import inspect

from worker_extraction.tasks import extract_fact


def test_inspect_extract_fact():
    print(f"\ntype(extract_fact): {type(extract_fact)}")
    print(f"hasattr(extract_fact, 'run'): {hasattr(extract_fact, 'run')}")
    print(f"type(extract_fact.run): {type(extract_fact.run)}")
    
    if hasattr(extract_fact.run, "__func__"):
        print("extract_fact.run has __func__ (it is a bound method)")
        sig = inspect.signature(extract_fact.run.__func__)
        print(f"Unbound Signature: {sig}")
    else:
        print("extract_fact.run does NOT have __func__")
        sig = inspect.signature(extract_fact.run)
        print(f"Signature: {sig}")
