import inspect

from worker_extraction.tasks import extract_fact


def test_inspect_signature():
    sig = inspect.signature(extract_fact.__wrapped__)
    print(f"\nSignature: {sig}")
    for name, param in sig.parameters.items():
        print(f"  {name}: {param.kind}")
