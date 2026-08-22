- [Fix] deploy.sh waits for the api socket to answer /healthz after restart before verify.sh
      runs; the v0.20 deploy read six 000s from a socket uvicorn had not re-bound yet
