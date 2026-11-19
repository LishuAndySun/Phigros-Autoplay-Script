"""Export every Unity AudioClip from phigros_base.apk to WAV using vgmstream-cli."""
import hashlib
import io
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from binary_reader import BinaryReader  # noqa: E402
import extract as ex  # noqa: E402

APK = ROOT / 'phigros_base.apk'
OUT = ROOT / 'Assets' / 'Audio'
VGMSTREAM = shutil.which('vgmstream-cli') or '/opt/homebrew/bin/vgmstream-cli'


def read_audio_clip(r: ex.ObjectReader):
    r.pos = r.byte_start
    name = r.aligned_string()
    r.i32  # load type
    r.i32  # channels
    r.i32  # frequency
    r.i32  # bits per sample
    r.f32  # length
    r.bool
    r.bool
    r.align(4)
    r.i32  # subsound index
    r.bool
    r.bool
    r.bool
    r.align(4)
    source = r.aligned_string()
    offset = r.u64
    size = r.u64
    return name, source, offset, size


def safe_name(name: str) -> str:
    return re.sub(r'[^\w\-. ]', '_', name).strip() or 'unnamed'


def main():
    stats = {'exported': 0, 'duplicate': 0, 'no_resource': 0, 'decode_fail': 0, 'bundle_parse_fail': 0}
    seen_hashes: set[str] = set()
    failures: list[str] = []

    with zipfile.ZipFile(APK) as z, tempfile.TemporaryDirectory() as tmp_dir:
        infos = z.infolist()
        dir_resources: dict[str, BinaryReader] = {}
        for info in infos:
            if info.filename.startswith('assets/bin/Data/') and info.filename.endswith('.resource'):
                dir_resources[pathlib.PurePosixPath(info.filename).name] = BinaryReader(z.open(info))

        sources = []
        for info in infos:
            if info.is_dir() or info.filename.endswith(('.json', '.resource')):
                continue
            if info.filename.startswith('assets/aa/Android/'):
                sources.append(('aa', info))
            elif info.filename.startswith('assets/bin/Data/') and info.filename.count('/') == 3:
                sources.append(('bin', info))

        for group, info in sources:
            path = pathlib.PurePosixPath(info.filename)
            manager = ex.AssetsManager()
            manager.resource_file_readers.update(dir_resources)
            data = z.read(info)
            try:
                reader = ex.FileReader(io.BytesIO(data), ROOT / path.name)
                if reader.file_type == ex.FileReader.FileType.BundleFile:
                    manager.load_bundle(reader)
                elif reader.file_type == ex.FileReader.FileType.AssetsFile:
                    manager.load_assets(reader, ROOT / path.name, '', None)
                else:
                    continue
            except Exception as e:
                stats['bundle_parse_fail'] += 1
                failures.append(f'{info.filename}: {type(e).__name__}: {e}')
                continue

            for asset_file in manager.asset_files:
                for object_info in asset_file.object_infos:
                    if object_info.class_id != ex.ClassID.AUDIO_CLIP:
                        continue
                    with ex.ObjectReader(asset_file.reader, asset_file, object_info) as obj_reader:
                        name, source, offset, size = read_audio_clip(obj_reader)
                    resource_name = pathlib.PurePosixPath(source.split(':', 1)[-1]).name
                    resource = manager.resource_file_readers.get(resource_name)
                    if not source or resource is None:
                        stats['no_resource'] += 1
                        failures.append(f'{info.filename}: no resource for {name!r} ({source!r})')
                        continue
                    resource.pos = offset
                    blob = resource.read(size)
                    digest = hashlib.sha1(blob).hexdigest()
                    if digest in seen_hashes:
                        stats['duplicate'] += 1
                        continue
                    seen_hashes.add(digest)

                    out_dir = OUT / group
                    out_dir.mkdir(parents=True, exist_ok=True)
                    out_path = out_dir / f'{safe_name(name)}__{digest[:10]}.wav'
                    fsb_path = pathlib.Path(tmp_dir) / f'{digest}.fsb'
                    fsb_path.write_bytes(blob)
                    result = subprocess.run([VGMSTREAM, '-o', str(out_path), str(fsb_path)],
                                            capture_output=True, text=True)
                    if result.returncode != 0 or not out_path.exists():
                        stats['decode_fail'] += 1
                        failures.append(f'{info.filename}: decode failed for {name!r}: {result.stderr.strip()[:120]}')
                        continue
                    stats['exported'] += 1

    print(stats)
    if failures:
        print(f'{len(failures)} issues, first 20:')
        for line in failures[:20]:
            print(' ', line)


if __name__ == '__main__':
    main()
