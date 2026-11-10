import socket
import struct
import subprocess
import threading
import time
import os

# scrcpy 服务端版本必须与文件版本、以及 Server 参数中的版本完全一致
SERVER_VERSION = '2.7'
SERVER_FILENAME = f'scrcpy-server-v{SERVER_VERSION}'
REMOTE_SERVER_PATH = '/data/local/tmp/scrcpy-server.jar'
SOCKET_NAME = 'scrcpy'
ACCEPT_TIMEOUT = 15  # 秒

ACTION_DOWN = 0
ACTION_UP = 1
ACTION_MOVE = 2
MSG_TYPE_INJECT_TOUCH_EVENT = 2
GENERIC_FINGER_ID = 0xffffffffffffffff
# type, action, pointer_id, x, y, screen_w, screen_h, pressure, action_button, buttons (共 32 字节)
TOUCH_FMT = '!BBQiiHHHII'
TOUCH_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'touch_log.tsv')  # 实际发出的触控日志


def _kill_stale_servers():
    '''结束设备上残留的 scrcpy 服务端（上次运行被中断时会遗留，导致触控包尺寸与当前服务端不一致）'''
    # [c]om 用于避免 pkill 匹配到自己的 shell 命令行
    subprocess.run(['adb', 'shell', 'pkill -f [c]om.genymobile.scrcpy.Server'])


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    '''读取恰好 n 字节，处理 TCP 分片'''
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError('scrcpy 连接已关闭')
        buf += chunk
    return bytes(buf)


class DeviceController:
    video_socket: socket.socket
    control_socket: socket.socket
    server_process: subprocess.Popen
    garbage_collector: threading.Thread
    device_size: tuple[int, int]
    collector_running: bool

    def __init__(self, port: int = 27183, push_server: bool = True, server_dir: str = '.'):
        server_file = os.path.join(server_dir, SERVER_FILENAME)
        if not os.path.isfile(server_file):
            raise FileNotFoundError(f'找不到 {server_file}，请下载 scrcpy {SERVER_VERSION} 服务端')
        _kill_stale_servers()
        if push_server:
            subprocess.run(['adb', 'push', server_file, REMOTE_SERVER_PATH], check=True)
        subprocess.run(['adb', 'reverse', f'localabstract:{SOCKET_NAME}', f'tcp:{port}'], check=True)

        skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        skt.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        skt.bind(('localhost', port))
        skt.listen(2)
        skt.settimeout(ACCEPT_TIMEOUT)

        # 注意: 服务端参数顺序固定，第一个参数必须是版本号
        self.server_process = subprocess.Popen(
            ['adb', 'shell', f'CLASSPATH={REMOTE_SERVER_PATH}', 'app_process', '/',
             'com.genymobile.scrcpy.Server',
             SERVER_VERSION,
             'log_level=warn',
             'video_bit_rate=8000000',
             'clipboard_autosync=false',
             'audio=false',  # 默认会开启音频并多占用一个 socket，必须关闭
             ])
        try:
            # 反向隧道下服务端按 视频 -> 控制 的顺序连接
            self.video_socket, _ = skt.accept()
            self.control_socket, _ = skt.accept()
            self.video_socket.settimeout(None)
            self.control_socket.settimeout(None)
        except OSError as e:
            self.server_process.kill()
            raise ConnectionError(f'scrcpy 服务端未能连接，请检查 adb 与服务端版本: {e}') from e
        finally:
            skt.close()
            subprocess.run(['adb', 'reverse', '--remove', f'localabstract:{SOCKET_NAME}'])  # 禁用adb tunnel

        self.collector_running = True

        # 握手: 服务端直接发送 64 字节设备名，然后是 编码(4) + 宽(4) + 高(4)，无 dummy 字节
        _device_name = _recv_exact(self.video_socket, 64)
        _codec_id, width, height = struct.unpack('!III', _recv_exact(self.video_socket, 12))
        self.device_size = width, height

        def collector():
            '''垃圾收集器
            实际上我们并不需要scrcpy-server传来的视频数据，
            但如果我们不接收这些数据，server就会崩溃，所以这个线程专门用来接受这些数据，
            然后把它们丢到虚空'''
            try:
                while self.collector_running:
                    # 帧头: pts(8 字节) + 包长度(4 字节)
                    _pts, size = struct.unpack('!qI', _recv_exact(self.video_socket, 12))
                    _recv_exact(self.video_socket, size)
            except (OSError, ConnectionError, struct.error) as e:
                print(f'[control] 视频接收线程退出: {e!r}')
                self.collector_running = False

        def ctrlmsg_receiver():
            '''另一个垃圾收集器
            收集的是scrcpy-server传来的设备消息（剪贴板、ACK 等）
            '''
            try:
                while self.collector_running:
                    msg_type = _recv_exact(self.control_socket, 1)[0]
                    if msg_type == 0:  # DEVICE_MSG_TYPE_CLIPBOARD: 长度(4) + 文本
                        size, = struct.unpack('!I', _recv_exact(self.control_socket, 4))
                        _recv_exact(self.control_socket, size)
                    elif msg_type == 1:  # DEVICE_MSG_TYPE_ACK_CLIPBOARD: sequence(8)
                        _recv_exact(self.control_socket, 8)
                    else:
                        raise ConnectionError(f'未知设备消息类型 {msg_type}')
            except (OSError, ConnectionError, struct.error) as e:
                print(f'[control] 控制接收线程退出: {e!r}')
                self.collector_running = False

        self.garbage_collector = threading.Thread(target=collector, daemon=True)
        self.garbage_collector.start()

        self.control_collector = threading.Thread(target=ctrlmsg_receiver, daemon=True)
        self.control_collector.start()


    def close(self):
        self.collector_running = False
        for sock in (self.video_socket, self.control_socket):
            try:
                sock.close()
            except OSError:
                pass
        self.server_process.kill()
        _kill_stale_servers()

    def _send_touch(self, x: int, y: int, action: int, pressure: int, pointer_id: int):
        packet = struct.pack(TOUCH_FMT, MSG_TYPE_INJECT_TOUCH_EVENT, action, pointer_id,
                             x, y, *self.device_size, pressure, 0, 0)
        self.control_socket.sendall(packet)
        with open(TOUCH_LOG_PATH, 'a') as f:
            f.write(f'{time.time():.3f}\t{action}\t{pointer_id}\t{x}\t{y}\t{self.device_size[0]}x{self.device_size[1]}\n')

    def touch(self, x: int, y: int, action: int, pressure: int = 0xffff, pointer_id: int = GENERIC_FINGER_ID):
        self._send_touch(x, y, action, pressure, pointer_id)

    def touch_down(self, x: int, y: int, pressure: int = 0xffff, pointer_id: int = GENERIC_FINGER_ID):
        self._send_touch(x, y, ACTION_DOWN, pressure, pointer_id)

    def touch_move(self, x: int, y: int, pressure: int = 0xffff, pointer_id: int = GENERIC_FINGER_ID):
        self._send_touch(x, y, ACTION_MOVE, pressure, pointer_id)

    def touch_up(self, x: int, y: int, pressure: int = 0xffff, pointer_id: int = GENERIC_FINGER_ID):
        self._send_touch(x, y, ACTION_UP, pressure, pointer_id)

    def tap(self, x: int, y: int, pointer_id: int = GENERIC_FINGER_ID, pressure: int = 0xffff):
        self.touch_down(x, y, pressure, pointer_id)
        self.touch_up(x, y, pressure, pointer_id)


if __name__ == '__main__':
    ids = 0
    ctl = DeviceController()
    while True:
        print(f'tap {ids}')
        ctl.touch_down(200, 200, pointer_id=ids)
        ids += 1
        time.sleep(0.6)
