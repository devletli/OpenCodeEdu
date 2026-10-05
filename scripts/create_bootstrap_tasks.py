import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kiraci.store import Store


def main():
    db_path = os.environ.get("KIRACI_DB", "data/kiraci.db")
    print(f"Using database: {db_path}", flush=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    store = Store(conn)

    task1 = store.add_human_task(
        kind="account_setup",
        title="Set up Lemon Squeezy payment account",
        instructions="""1. Go to https://lemonsqueezy.com and create an account in your name (the human owner)
2. Verify your email and complete identity verification if required
3. Create a new store for digital products
4. Go to Settings > API and create an API key with read/write permissions
5. Copy the API key and store ID
6. Add these to your .env file as LEMONSQUEEZY_API_KEY=your_key_here and LEMONSQUEEZY_STORE_ID=your_store_id
7. In Settings > Payments, add your bank account or payment method for receiving payouts
8. Mark this task as done when complete""",
        url="https://lemonsqueezy.com",
        dedupe_key="lemonsqueezy-account-setup",
        created_by="brain",
    )
    print(f"Task 1 result: {task1}", flush=True)

    task2 = store.add_human_task(
        kind="account_setup",
        title="Register a domain for product landing pages",
        instructions="""1. Choose a domain registrar (Namecheap, Cloudflare, or similar - choose one with competitive pricing around EUR 10-15/year)
2. Search for an available domain name suitable for digital products (short, memorable, .com or .io preferred)
3. Purchase the domain (1 year minimum)
4. Keep the domain management dashboard accessible for future DNS configuration
5. Add the domain name to your .env file as KIRACI_DOMAIN=yourdomain.com
6. Mark this task as done when complete""",
        url="https://www.namecheap.com",
        dedupe_key="domain-registration",
        created_by="brain",
    )
    print(f"Task 2 result: {task2}", flush=True)

    conn.close()
    print("\nDone!", flush=True)


if __name__ == "__main__":
    main()