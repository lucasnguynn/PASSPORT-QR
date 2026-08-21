# Digital Product Passport

Open-source modular-monolith foundation for a jewelry Digital Product Passport. Copy `.env.example` to `.env`, generate the ECDSA keys, and run `docker compose up --build`.

```bash
cp .env.example .env
python scripts/generate_keys.py
docker compose up --build
```
