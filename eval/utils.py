"""eval 工具：复刻系统分块逻辑、数据集加载、chunk 索引构建、网络环境补丁。"""
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from main import MedicalSystem  # noqa: E402
from config import MEDICAL_DOCS_DIR  # noqa: E402

CHUNK_INDEX_PATH = os.path.join(PROJECT_ROOT, "eval", "datasets", "chunk_index.json")


def patch_requests_ssl():
    """环境补丁：本机存在本地代理（127.0.0.1）拦截 HTTPS，导致 DashScope API
    调用出现 SSLCertVerificationError。对 requests 打补丁跳过证书校验。

    注意：仅作用于测评进程，不修改被测系统（utils/llm_client.py / rag/embedding.py）。
    """
    try:
        import requests
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        _orig_session_request = requests.Session.request
        _orig_api_request = requests.request

        def _session_request(self, method, url, **kwargs):
            kwargs["verify"] = False
            return _orig_session_request(self, method, url, **kwargs)

        def _api_request(method, url, **kwargs):
            kwargs["verify"] = False
            return _orig_api_request(method, url, **kwargs)

        requests.Session.request = _session_request
        requests.request = _api_request
    except ImportError:
        pass


def build_chunk_index(docs_dir: str = MEDICAL_DOCS_DIR) -> dict:
    """按 main.MedicalSystem._split_into_chunks 的完全相同逻辑切分文档，
    返回 {chunk_id: {"document": str, "source": filename, "chunk_index": i}}。
    chunk_id 与 main.py init_rag 中生成的 id 完全一致（filename_i）。
    """
    index = {}
    for filename in sorted(os.listdir(docs_dir)):
        if not filename.endswith(".txt"):
            continue
        filepath = os.path.join(docs_dir, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        chunks = MedicalSystem._split_into_chunks(content, chunk_size=500, overlap=50)
        for i, chunk in enumerate(chunks):
            index[f"{filename}_{i}"] = {
                "document": chunk,
                "source": filename,
                "chunk_index": i,
            }
    return index


def load_chunk_index(refresh: bool = False) -> dict:
    """加载 chunk 索引；不存在或要求刷新时重新构建并落盘。"""
    if not refresh and os.path.exists(CHUNK_INDEX_PATH):
        with open(CHUNK_INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    index = build_chunk_index()
    os.makedirs(os.path.dirname(CHUNK_INDEX_PATH), exist_ok=True)
    with open(CHUNK_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    return index


def load_dataset(name: str) -> list[dict]:
    """加载 eval/datasets/{name}.jsonl。"""
    path = os.path.join(PROJECT_ROOT, "eval", "datasets", name)
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


if __name__ == "__main__":
    index = load_chunk_index(refresh=True)
    print(f"共 {len(index)} 个 chunk：")
    for cid, info in index.items():
        print(f"  {cid}  [{info['source']}]  {len(info['document'])}字")
