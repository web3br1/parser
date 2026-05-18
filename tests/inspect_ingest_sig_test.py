import inspect

from worker_ingest.tasks import ingest_source


def test_inspect_ingest_signature():
    # .run is the function itself
    sig = inspect.signature(ingest_source.run)
    print(f"\nIngest Signature: {sig}")
    for name, param in sig.parameters.items():
        print(f"  {name}: {param.kind}")
