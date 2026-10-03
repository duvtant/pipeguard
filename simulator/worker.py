"""Historian simulator (stub). Owner: Ebube. Spec: docs/techstack.md section 8.

Placeholder loop so `docker compose up` stays healthy until the real simulator lands.
"""
import time

if __name__ == "__main__":
    print("simulator worker: stub running", flush=True)
    while True:
        time.sleep(30)
        print("simulator worker: stub heartbeat", flush=True)
