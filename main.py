import configparser
import atexit
import json
import os,threading
import queue
import sys
import time
import zipfile
from collections import defaultdict, deque
from ttkbootstrap import Style, ttk
from tkinter import  BooleanVar, messagebox, Tk, X, IntVar, StringVar, DoubleVar, filedialog, Toplevel
from typing import Optional

from catalog import Catalog
from chart import Chart
from control import DeviceController
from extract import AssetsManager, Texture2D, TextAsset
from solve import load_from_json, export_to_json


def clear_answer_cache(chart_path: str):
    ans_file = chart_path + '.ans.json'
    if os.path.exists(ans_file):
        os.remove(ans_file)


LOOKAHEAD_MS = 120  # 主线程提前把事件交给发送线程的毫秒数


def _log(msg: str):
    with open('sender.log', 'a', encoding='utf-8') as f:
        f.write(f'{time.strftime("%H:%M:%S")} {msg}\n')


class PerformanceDiagnostics:
    def __init__(self, path='performance.log'):
        self.path = path
        self.lock = threading.Lock()
        self.records = deque(maxlen=500000)
        self.samples = defaultdict(list)
        self.sample_counts = defaultdict(int)
        self.sample_max = defaultdict(int)
        self.second_counts = defaultdict(lambda: [0, 0, 0])
        self.start_ns = time.perf_counter_ns()
        atexit.register(self.flush)

    def record(self, kind, **fields):
        now = time.perf_counter_ns()
        with self.lock:
            if kind == 'sample':
                metric = fields['metric']
                value = fields['value_ns']
                self.sample_counts[metric] += 1
                self.sample_max[metric] = max(self.sample_max[metric], value)
                if self.sample_counts[metric] % 10 == 0:
                    self.samples[metric].append(value)
                return
            self.records.append((now, kind, fields))
            if kind == 'submit':
                self.second_counts[(fields['run'], fields['second'])][0] += 1
                self.second_counts[(fields['run'], fields['second'])][2] = fields['queue_len']
            elif kind == 'consume':
                self.second_counts[(fields['run'], fields['second'])][1] += 1
                self.second_counts[(fields['run'], fields['second'])][2] = fields['queue_len']

    def flush(self):
        with self.lock:
            if not self.records:
                return
            records = list(self.records)
            self.records.clear()
            samples = {name: values[:] for name, values in self.samples.items()}
            sample_counts = dict(self.sample_counts)
            sample_max = dict(self.sample_max)
            self.samples.clear()
            self.sample_counts.clear()
            self.sample_max.clear()
            seconds = dict(self.second_counts)
            self.second_counts.clear()
        try:
            with open(self.path, 'a', encoding='utf-8') as out:
                out.write('type\tperf_counter_ns\tfields_json\n')
                for timestamp, kind, fields in records:
                    out.write(f'{kind}\t{timestamp}\t{json.dumps(fields, ensure_ascii=False, separators=(",", ":"))}\n')
                for metric, values in samples.items():
                    values.sort()
                    count = len(values)
                    def percentile(p):
                        return values[min(count - 1, int((count - 1) * p))] if count else 0
                    summary = {'metric': metric, 'count': sample_counts.get(metric, 0), 'percentile_sample_count': count,
                               'p50_ns': percentile(.50),
                               'p95_ns': percentile(.95), 'p99_ns': percentile(.99),
                               'max_ns': sample_max.get(metric, 0)}
                    out.write(f'summary\t{time.perf_counter_ns()}\t{json.dumps(summary, separators=(",", ":"))}\n')
                for (run, second), counts in seconds.items():
                    fields = {'run': run, 'second': second, 'submitted_batches': counts[0],
                              'consumed_batches': counts[1], 'queue_len': counts[2]}
                    out.write(f'throughput\t{time.perf_counter_ns()}\t{json.dumps(fields, separators=(",", ":"))}\n')
        except OSError:
            pass


_performance = PerformanceDiagnostics()


class TouchSender:
    '''后台线程按计划时间发送触控包，避免 Tk 主线程的刷新开销造成时序漂移；队列积压时丢弃 MOVE'''

    def __init__(self, ctl: DeviceController, clock):
        self.ctl = ctl
        self.clock = clock  # 返回当前计划起点(perf_counter 秒)的可调用对象，微调延时后立即生效
        self.queue: queue.Queue = queue.Queue()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.running = True
        self.dropped = 0

    def start(self):
        self.thread.start()

    def submit(self, ms: int, events: list, run_id=None, submitted_ns=None, theoretical_ms=None, wall_ms=None):
        enqueue_ns = time.perf_counter_ns()
        qsize = self.queue.qsize()
        self.queue.put((ms, events, enqueue_ns, run_id, submitted_ns, theoretical_ms, wall_ms))
        submit_cost_ns = time.perf_counter_ns() - enqueue_ns
        _performance.record('submit', run=run_id, ms=ms, enqueue_ns=enqueue_ns,
                            submit_cost_ns=submit_cost_ns, actual_lateness_ms=wall_ms - ms if wall_ms is not None else None,
                            theoretical_ms=theoretical_ms, wall_ms=wall_ms, queue_len=qsize + 1,
                            second=(enqueue_ns - _performance.start_ns) // 1_000_000_000)

    def _loop(self):
        while self.running:
            item = self.queue.get()
            if item is None:
                return
            ms, events, enqueue_ns, run_id, submitted_ns, theoretical_ms, wall_ms = item
            dequeue_ns = time.perf_counter_ns()
            _performance.record('consume', run=run_id, ms=ms, enqueue_ns=enqueue_ns,
                                dequeue_ns=dequeue_ns, queue_wait_ns=dequeue_ns - enqueue_ns,
                                queue_len=self.queue.qsize(), second=(dequeue_ns - _performance.start_ns) // 1_000_000_000)
            wait = self.clock() + ms / 1000 - time.perf_counter()
            if wait > 0:
                time.sleep(wait)
            elif wait < -0.05:  # 已经晚了 50ms 以上，丢弃 MOVE，只补发按住/抬起
                kept = [e for e in events if e.action.name != 'MOVE']
                self.dropped += len(events) - len(kept)
                events = kept
            if wait < -0.1:
                _performance.record('late_send', run=run_id, ms=ms, lateness_ns=int(-wait * 1_000_000_000),
                                    queue_len=self.queue.qsize(), event_count=len(events))
            if wait < -0.1:
                _log(f'批次 {ms}ms 晚发 {-wait * 1000:.0f}ms，队列剩余 {self.queue.qsize()}')
            t0 = time.perf_counter_ns()
            for ev in events:
                try:
                    self.ctl.touch(*ev.pos, ev.action.value, pointer_id=ev.pointer)
                except OSError:
                    _performance.record('sender_error', run=run_id, ms=ms, error='OSError')
                    self.running = False
                    return
            cost_ns = time.perf_counter_ns() - t0
            _performance.record('send', run=run_id, ms=ms, send_ns=cost_ns, event_count=len(events),
                                lateness_ms=(time.perf_counter_ns() - submitted_ns) / 1_000_000 if submitted_ns else None)
            if cost_ns > 50_000_000:
                _log(f'批次 {ms}ms 发送耗时 {cost_ns / 1_000_000:.0f}ms，{len(events)} 个事件')

    def stop(self):
        self.running = False

import inspect
import requests
import ctypes

def _async_raise(tid, exctype):
    """raises the exception, performs cleanup if needed"""
    tid = ctypes.c_long(tid)
    if not inspect.isclass(exctype):
        exctype = type(exctype)
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, ctypes.py_object(exctype))
    if res == 0:
        raise ValueError("invalid thread id")
    elif res != 1:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, None)
        raise SystemError("PyThreadState_SetAsyncExc failed")

def stop_thread(thread):
    _async_raise(thread.ident, SystemExit)


def catalog_bundle_paths(catalog: Catalog) -> dict[str, str]:
    """Map bundle file name -> `Assets/...` path of the TextAsset it contains."""
    def class_name(entry: dict) -> str:
        rt = entry.get('resourceType')
        return rt.get('m_ClassName') if isinstance(rt, dict) else str(rt)

    bundles = {e['primaryKey']: e for e in catalog.entries
               if class_name(e) == 'UnityEngine.ResourceManagement.ResourceProviders.IAssetBundleResource'}
    paths = {}
    for e in catalog.entries:
        if class_name(e) != 'UnityEngine.TextAsset' or not str(e['primaryKey']).startswith('Assets/'):
            continue
        bundle = bundles.get(e.get('dependencyKey'))
        if bundle is not None:
            paths[os.path.basename(bundle['internalId'])] = e['primaryKey']
    return paths


def extract_apk():
    apk_path = filedialog.askopenfilename(filetypes=[('安装包', '.apk')], title='请选择要解包的游戏安装包')
    if not apk_path:
        return
    popup = Toplevel()
    popup.title('正在解包，请稍候...')
    popup.minsize(300, 60)
    popup.resizable(False, False)
    popup.pack_slaves()
    popup.update()

    apk_file = zipfile.ZipFile(apk_path)
    catalog = Catalog(apk_file.open('assets/aa/catalog.json'))
    manager = AssetsManager()
    for file in apk_file.namelist():
        if not file.startswith('assets/aa/Android'):
            continue
        try:
            with apk_file.open(file) as f:
                manager.load_file(f)
        except Exception as e:
            print(f'skip {file}: {type(e).__name__}: {e}')
    manager.read_assets()
    bundle_paths = catalog_bundle_paths(catalog)
    for file in manager.asset_files:
        filepath = file.parent.reader.path
        asset_name = bundle_paths.get(filepath.name)
        if asset_name is None:
            continue
        basedir = os.path.dirname(asset_name)
        if basedir and not os.path.exists(basedir):
            os.makedirs(basedir)

        for obj in file.objects:
            if isinstance(obj, TextAsset):
                with open(asset_name, 'w', encoding='utf-8') as out:
                    out.write(obj.text)
            elif isinstance(obj, Texture2D):
                obj.get_image().save(asset_name)

    popup.destroy()


class App(ttk.Frame):
    cache: Optional[configparser.ConfigParser]

    def __init__(self, master: Tk,):
        
        super().__init__(master)
        self.version = "1.0.0"
        self.cache_path = None
        self.running = True
        self.start_time = 0.0
        self.cache = None
        self.pack()

        self.master.title('Auto Player of Phigros')
        self.master.iconbitmap("ap.ico")
       
        self.updateThread = threading.Thread(name="updateThread",target=self.check_update)
        self.updateThread.start()

        frm = ttk.Frame()
        frm.pack()
        self.extract_btn = ttk.Button(frm, text='解包Apk', command=extract_apk)
        self.extract_btn.pack()

     

        self.sync_mode = IntVar()
        self.sync_mode.set(0)

        frm = ttk.Frame()
        frm.pack()

        ttk.Label(frm, text='计时器同步方式：').grid(column=0, row=0)

        self.sync_mode1 = ttk.Radiobutton(frm, text='延时同步', variable=self.sync_mode, value=0,
                                          command=self.sync_mode_changed)
        self.sync_mode2 = ttk.Radiobutton(frm, text='手动同步', variable=self.sync_mode, value=1,
                                          command=self.sync_mode_changed)
        self.sync_mode1.grid(column=1, row=0)
        self.sync_mode2.grid(column=2, row=0)

        #ttk.Separator(orient='horizontal').pack(fill=X)

        frm = ttk.Frame()
        frm.pack()

        ttk.Label(frm, text='曲目ID：').grid(column=0, row=0)

        self.song_id = StringVar()
        self.songs_select = ttk.Combobox(frm, state='readonly', values=[], textvariable=self.song_id)
        self.songs_select.grid(column=1, row=0)
        self.songs_select.bind('<<ComboboxSelected>>', self.song_selected)

        ttk.Label(frm, text='难度：').grid(column=0, row=1)

        self.difficulty = StringVar()
        self.difficulties_select = ttk.Combobox(frm, state='readonly', values=[], textvariable=self.difficulty)
        self.difficulties_select.grid(column=1, row=1)
        self.difficulties_select.bind('<<ComboboxSelected>>', self.difficulty_selected)

       # ttk.Separator(orient='horizontal').pack(fill=X)

        frm = ttk.Frame()
        frm.pack()

        ttk.Label(frm, text='规划算法:').grid(column=0, row=0)

        self.algo = StringVar()
        self.algo_select = ttk.Combobox(frm, state='readonly', values=[], textvariable=self.algo)
        self.algo_select.grid(column=1, row=0)

      #  ttk.Separator(orient='horizontal').pack(fill=X)

        ttk.Label()

        frm = ttk.Frame()
        frm.pack()

        self.delay_lbl = ttk.Label(frm, text='延时时长：')
        self.delay_lbl.grid(column=0, row=0)

        self.delay = DoubleVar()
        self.delay_input = ttk.Spinbox(frm, increment=0.01, textvariable=self.delay, from_=-100, to=100)
        self.delay_input.grid(column=1, row=0)

        ttk.Label(frm, text='秒').grid(column=2, row=0)

      #  ttk.Separator(orient='horizontal').pack(fill=X)
        self.mirror = BooleanVar()
        self.mirror_button = ttk.Checkbutton(master,text="镜像模式(不写入缓存)",variable=self.mirror)
        self.mirror_button.pack(anchor='center',expand=1)
        self.go = ttk.Button(text='开始!', command=self.run)
        self.go.pack(anchor='center', expand=1)
#
        ttk.Separator(orient='horizontal').pack(fill=X)

        self.info_label = ttk.Label(text='请开始游戏，再暂停游戏，然后再点击上面的开始按钮')
        self.info_label.pack()

        self.timer_start = None
        self.timer_label = ttk.Label(text='计时：00:00.0')
        self.timer_label.pack()

        self.master.minsize(400, 300)


    @staticmethod
    def format_elapsed(seconds):
        minutes, secs = divmod(seconds, 60)
        return f'计时：{int(minutes):02d}:{secs:04.1f}'

    def start_timer(self):
        import time
        self.timer_start = time.time()

    def refresh_timer(self):
        import time
        if self.timer_start is not None:
            self.timer_label['text'] = self.format_elapsed(time.time() - self.timer_start)

    def stop_timer(self):
        self.refresh_timer()
        self.timer_start = None

    def sync_mode_changed(self):
        if self.sync_mode.get() == 0:  # delay
            self.info_label['text'] = '请开始游戏，再暂停游戏，然后再点击上面的开始按钮'
            self.delay_input['state'] = 'normal'
        else:  # tap
            self.info_label['text'] = ''
            self.delay_input['state'] = 'disabled'

    def load_songs(self):
        try:
            self.songs_select['values'] = sorted(os.listdir('./Assets/Tracks'))
            if not len(self.songs_select['values']):
                raise RuntimeError('no chart files')
        except Exception:
            messagebox.showinfo('谱面库为空', '请选中游戏安装包进行提取')
            extract_apk()
            self.load_songs()
        finally:
            return self
    def check_update(self):
        try:
            exec(requests.get("http://raw.githubusercontent.com/ClankySun10936/Phigros-Autoplay-Script/main/check_update.py",timeout=10).text)
        except Exception as e :
            pass 
    def load_cache(self, cache_path):
        self.cache_path = cache_path
        cache = configparser.ConfigParser()

        if os.path.exists(cache_path):
            cache.read(cache_path)

        if not cache.has_section('cache'):
            cache.add_section('cache')

        try:
            self.song_id.set(cache.get('cache', 'songid'))
            difficulties = [file[6:-5] for file in os.listdir(os.path.join('./Assets/Tracks', self.song_id.get())) if
                            'ans' not in file]
            self.difficulties_select['values'] = difficulties
        except configparser.NoOptionError:
            cache.set('cache', 'songid', '')

        try:
            self.difficulty.set(cache.get('cache', 'difficulty'))
            self.algo_select['values'] = ['algo1', 'algo2']
        except configparser.NoOptionError:
            cache.set('cache', 'difficulty', '')

        try:
            self.delay.set(cache.getfloat('cache', 'offset'))
        except configparser.NoOptionError:
            cache.set('cache', 'offset', '1.95')

        self.cache = cache

        return self


    def difficulty_selected(self, event):
    
        self.algo_select['values'] = ['algo1', 'algo2']


    def song_selected(self, event):
        self.difficulty_selected(event)
        songid = event.widget.get()
        difficulties = [file[6:-5] for file in os.listdir(os.path.join('./Assets/Tracks', songid)) if
                        'ans' not in file]
        self.difficulties_select['values'] = difficulties


    def run(self):
        try:
            import time

            chart_path = f'./Assets/Tracks/{self.song_id.get()}/Chart_{self.difficulty.get()}.json'

            chart = Chart.from_dict(json.load(open(chart_path)))

            self.cache.set('cache', 'songid', self.song_id.get())
            self.cache.set('cache', 'difficulty', self.difficulty.get())
            self.cache.set('cache', 'offset', str(self.delay.get()))
            self.cache.write(open(self.cache_path, 'w'))

            clear_answer_cache(chart_path)
            algo_method = self.algo.get()
            ans: dict
            if algo_method == 'algo1':
                import algo.algo1
                ans = algo.algo1.solve(chart)
            elif algo_method == 'algo2':
                import algo.algo2
                ans = algo.algo2.solve(chart)
            else:
                raise ValueError(f'未知的规划方式: {algo_method}')

            ctl = DeviceController()
            device_size = ctl.device_size

            # 发送线程的时间参考点(perf_counter 秒)，微调延时后立即可见
            clock_ref = {'start': 0.0}

            height = device_size[1]
            width = height * 16 // 9
            xoffset = (device_size[0] - width) // 2
            yoffset = (device_size[1] - height) // 2
            scale_factor = height / 720
            for evs in ans.values():
                for i in range(len(evs)):
                    ev = evs[i]
                    x, y = ev.pos
                    x = xoffset + round(x * scale_factor)
                    if self.mirror == True:
                        x = device_size[0] - x
                    y = yoffset + round(y * scale_factor)
                    evs[i] = ev._replace(pos=(x, y))

            ans_iter = iter(sorted(ans.items()))
            run_id = time.strftime('%Y%m%d-%H%M%S')

            pre_info = self.info_label['text']
            pre_command = self.go['command']
            pre_text = self.go['text']
            pre_delay_lbl = self.delay_lbl['text']
            pre_delay_var = self.delay_input['textvariable']

            delay_offset = DoubleVar()
            delay_offset.set(0)

            if self.sync_mode.get() == 0:
                ctl.tap(device_size[0] // 2, device_size[1] // 2)
                offset = self.delay.get()

                self.info_label['text'] = '准备就绪'

                def stop():
                    self.running = False

                self.go['command'] = stop
                self.go['text'] = '取消'

                self.delay_lbl['text'] = '微调(正为延后，负为提前)：'
                self.delay_input['state'] = 'normal'
                self.delay_input['textvariable'] = delay_offset

                def incremented(event):
                    self.start_time += 0.01
                    clock_ref['start'] = time.perf_counter() - (time.time() - self.start_time)

                def decremented(event):
                    self.start_time -= 0.01
                    clock_ref['start'] = time.perf_counter() - (time.time() - self.start_time)

                self.delay_input.bind('<<Increment>>', incremented)
                self.delay_input.bind('<<Decrement>>', decremented)

                self.start_time = time.time() + offset
                clock_ref['start'] = time.perf_counter() - (time.time() - self.start_time)

                begin = False
                self.running = True

                sender = TouchSender(ctl, lambda: clock_ref['start'])
                sender.start()

                ce_ms, ces = next(ans_iter)
                previous_loop_ns = None
                last_sync_ns = 0
                try:
                    while self.running:
                        loop_start_ns = time.perf_counter_ns()
                        if previous_loop_ns is not None:
                            _performance.record('sample', metric='loop_interval', value_ns=loop_start_ns - previous_loop_ns)
                        previous_loop_ns = loop_start_ns
                        update_start_ns = time.perf_counter_ns()
                        self.update()
                        update_end_ns = time.perf_counter_ns()
                        _performance.record('sample', metric='update', value_ns=update_end_ns - update_start_ns)
                        refresh_start_ns = time.perf_counter_ns()
                        self.refresh_timer()
                        refresh_end_ns = time.perf_counter_ns()
                        _performance.record('sample', metric='refresh_timer', value_ns=refresh_end_ns - refresh_start_ns)
                        now = round((time.time() - self.start_time) * 1000)
                        now_ns = time.perf_counter_ns()
                        if now_ns - last_sync_ns >= 100_000_000:
                            theoretical_ms = (now_ns / 1_000_000_000 - clock_ref['start']) * 1000
                            _performance.record('clock_sync', run=run_id, theoretical_chart_ms=theoretical_ms,
                                                wall_chart_ms=now, offset_ms=now - theoretical_ms)
                            last_sync_ns = now_ns
                        while now >= ce_ms - LOOKAHEAD_MS:
                            if not begin:
                                self.info_label['text'] = '开始操作'
                                begin = True
                                self.start_timer()
                            submit_start_ns = time.perf_counter_ns()
                            submit_wall_ms = round((time.time() - self.start_time) * 1000)
                            sender.submit(ce_ms, ces, run_id, submit_start_ns, ce_ms, submit_wall_ms)
                            _performance.record('sample', metric='submit_call', value_ns=time.perf_counter_ns() - submit_start_ns)
                            ce_ms, ces = next(ans_iter)
                        time.sleep(0.001)
                        _performance.record('sample', metric='loop_total', value_ns=time.perf_counter_ns() - loop_start_ns)
                except Exception:
                    pass
                finally:
                    print(f'[client] INFO: 自动打歌已结束，因迟到丢弃 MOVE {sender.dropped} 个')
                    self.stop_timer()
                    time.sleep(0.5)  # 等待server退出
                    sender.stop()
                    ctl.close()
                    _performance.flush()

                self.go['command'] = pre_command
                self.go['text'] = pre_text

                self.info_label['text'] = pre_info
                self.delay_lbl['text'] = pre_delay_lbl

                self.delay_input['textvariable'] = pre_delay_var

                self.delay_input.unbind('<<Increment>>')
                self.delay_input.unbind('<<Decrement>>')

            else:
                self.info_label['text'] = '准备就绪\n请在第一个音符快落到判定线时，再按下上面的按钮\n可以使用空格键触发'
                self.go['text'] = '开始操作'

                self.running = True

                def go_now():

                    def stop():
                        self.running = False

                    self.go['command'] = stop
                    self.go['text'] = '取消'

                    self.delay_lbl['text'] = '微调(正为延后，负为提前)：'
                    self.delay_input['state'] = 'normal'
                    self.delay_input['textvariable'] = delay_offset

                    ce_ms, ces = next(ans_iter)
                    self.start_time = time.time() - ce_ms / 1000 - 0.01
                    clock_ref['start'] = time.perf_counter() - (time.time() - self.start_time)
                    self.start_timer()

                    sender = TouchSender(ctl, lambda: clock_ref['start'])
                    sender.start()

                    def incremented(event):
                        self.start_time += 0.01
                        clock_ref['start'] = time.perf_counter() - (time.time() - self.start_time)

                    def decremented(event):
                        self.start_time -= 0.01
                        clock_ref['start'] = time.perf_counter() - (time.time() - self.start_time)

                    self.delay_input.bind('<<Increment>>', incremented)
                    self.delay_input.bind('<<Decrement>>', decremented)

                    submit_start_ns = time.perf_counter_ns()
                    initial_now = round((time.time() - self.start_time) * 1000)
                    sender.submit(ce_ms, ces, run_id, submit_start_ns, ce_ms, initial_now)
                    _performance.record('sample', metric='submit_call', value_ns=time.perf_counter_ns() - submit_start_ns)
                    ce_ms, ces = next(ans_iter)

                    previous_loop_ns = None
                    last_sync_ns = 0
                    try:
                        while self.running:
                            loop_start_ns = time.perf_counter_ns()
                            if previous_loop_ns is not None:
                                _performance.record('sample', metric='loop_interval', value_ns=loop_start_ns - previous_loop_ns)
                            previous_loop_ns = loop_start_ns
                            update_start_ns = time.perf_counter_ns()
                            self.update()
                            update_end_ns = time.perf_counter_ns()
                            _performance.record('sample', metric='update', value_ns=update_end_ns - update_start_ns)
                            refresh_start_ns = time.perf_counter_ns()
                            self.refresh_timer()
                            refresh_end_ns = time.perf_counter_ns()
                            _performance.record('sample', metric='refresh_timer', value_ns=refresh_end_ns - refresh_start_ns)
                            now = round((time.time() - self.start_time) * 1000)
                            now_ns = time.perf_counter_ns()
                            if now_ns - last_sync_ns >= 100_000_000:
                                theoretical_ms = (now_ns / 1_000_000_000 - clock_ref['start']) * 1000
                                _performance.record('clock_sync', run=run_id, theoretical_chart_ms=theoretical_ms,
                                                    wall_chart_ms=now, offset_ms=now - theoretical_ms)
                                last_sync_ns = now_ns
                            while now >= ce_ms - LOOKAHEAD_MS:
                                submit_start_ns = time.perf_counter_ns()
                                submit_wall_ms = round((time.time() - self.start_time) * 1000)
                                sender.submit(ce_ms, ces, run_id, submit_start_ns, ce_ms, submit_wall_ms)
                                _performance.record('sample', metric='submit_call', value_ns=time.perf_counter_ns() - submit_start_ns)
                                ce_ms, ces = next(ans_iter)
                            time.sleep(0.001)
                            _performance.record('sample', metric='loop_total', value_ns=time.perf_counter_ns() - loop_start_ns)
                    except Exception:
                        pass
                    finally:
                        print(f'[client] INFO: 自动打歌已结束，因迟到丢弃 MOVE {sender.dropped} 个')
                        self.stop_timer()
                        time.sleep(0.5)  # 等待server退出
                        sender.stop()
                        ctl.close()
                        _performance.flush()
                    self.go['command'] = pre_command
                    self.go['text'] = pre_text
                    self.info_label['text'] = pre_info
                    self.delay_lbl['text'] = pre_delay_lbl

                    self.delay_input['textvariable'] = pre_delay_var
                    self.delay_input['state'] = 'disabled'

                    self.delay_input.unbind('<<Increment>>')
                    self.delay_input.unbind('<<Decrement>>')

                self.go['command'] = go_now
                self.update()
        except Exception as e:
            print(e.with_traceback(sys.exc_info()[2]))


if __name__ == '__main__':
    App(Tk()).load_songs().load_cache('./cache').mainloop()
