import fcntl
import hashlib
import os
import shutil
import tarfile
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from urllib.request import urlopen


ASR_MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-streaming-paraformer-bilingual-zh-en.tar.bz2"
)

MODEL_FILE_HASHES = {
    "encoder.int8.onnx": "81a70226a8934e6ed92aa1d4fc486b428b5398e2f2619ed4897b7294cab90e9a",
    "decoder.int8.onnx": "f3cca9f77bb9d93c8fcbfb63ae617b6b1ee96818df3aa3b151c40658fe38594f",
    "tokens.txt": "59aba8873a2ed1e122c25fee421e25f283b63290efbde85c1f01a853d83cb6e6",
}

_INSTALL_LOCK = threading.Lock()


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _model_files(directory, expected_hashes):
    directory = Path(directory)
    resolved = {}
    for name in expected_hashes:
        matches = list(directory.rglob(name)) if directory.exists() else []
        if len(matches) != 1 or not matches[0].is_file():
            return None
        resolved[name] = matches[0]
    return resolved


def validate_model_dir(directory, expected_hashes=MODEL_FILE_HASHES):
    files = _model_files(directory, expected_hashes)
    if files is None:
        return False
    return all(_sha256(files[name]) == expected for name, expected in expected_hashes.items())


def _download_and_extract(url, destination):
    destination = Path(destination)
    model_dir = destination / "sherpa-onnx-streaming-paraformer-bilingual-zh-en"
    model_dir.mkdir(parents=True, exist_ok=True)
    selected = set(MODEL_FILE_HASHES)
    extracted = set()

    with tempfile.NamedTemporaryFile(suffix=".tar.bz2") as archive:
        with urlopen(url, timeout=60) as response:
            shutil.copyfileobj(response, archive)
        archive.flush()
        with tarfile.open(archive.name, "r:bz2") as bundle:
            for member in bundle:
                name = Path(member.name).name
                if name not in selected or not member.isfile():
                    continue
                if name in extracted:
                    raise RuntimeError(f"模型压缩包包含重复文件：{name}")
                source = bundle.extractfile(member)
                if source is None:
                    raise RuntimeError(f"无法读取模型文件：{name}")
                with source, (model_dir / name).open("wb") as output:
                    shutil.copyfileobj(source, output)
                extracted.add(name)

    missing = selected - extracted
    if missing:
        raise RuntimeError(f"模型压缩包缺少必要文件：{', '.join(sorted(missing))}")


@contextmanager
def _installation_lock(parent):
    parent = Path(parent)
    parent.mkdir(parents=True, exist_ok=True)
    lock_path = parent / ".zhichun-model-install.lock"
    with _INSTALL_LOCK, lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def install_models(
    root,
    downloader=_download_and_extract,
    expected_hashes=MODEL_FILE_HASHES,
):
    root = Path(root)
    target = root / "asr"

    with _installation_lock(root.parent):
        if validate_model_dir(target, expected_hashes):
            return

        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".zhichun-model-", dir=root.parent) as temporary:
            staged = Path(temporary) / "asr"
            downloader(ASR_MODEL_URL, staged)
            if not validate_model_dir(staged, expected_hashes):
                raise RuntimeError("离线语音模型校验失败，请重新下载")

            backup = Path(temporary) / "previous-asr"
            had_previous = target.exists()
            if had_previous:
                os.replace(target, backup)
            try:
                os.replace(staged, target)
            except BaseException:
                if had_previous and backup.exists():
                    os.replace(backup, target)
                raise
