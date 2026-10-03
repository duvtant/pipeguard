"""Engine worker (stub). Owner: Olise. Spec: docs/techstack.md section 4.3.

Placeholder loop so `docker compose up` stays healthy until the real engine lands.
"""
import time

if __name__ == "__main__":
    print("engine worker: stub running", flush=True)
    while True:
        time.sleep(30)
        print("engine worker: stub heartbeat", flush=True)
