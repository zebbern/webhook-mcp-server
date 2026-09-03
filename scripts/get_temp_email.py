"""Quick script to create a webhook and get temp email."""
import asyncio
import os

from services.webhook_service import WebhookService
from utils.http_client import WebhookHttpClient


async def main():
    async with WebhookHttpClient(api_key=os.environ.get("WEBHOOK_SITE_API_KEY")) as client:
        service = WebhookService(client)
        result = await service.create()
        token = result.data["token"]

        print("=" * 60)
        print("YOUR TEMPORARY WEBHOOK ENDPOINTS")
        print("=" * 60)
        print(f"Token:  {token}")
        print(f"URL:    {result.data['url']}")
        print(f"Email:  {result.data['email']}")
        print(f"DNS:    {result.data['dns']}")
        print(f"Expiry: {result.data['expires_at'] or 'never'}")
        print("=" * 60)
        print("View incoming requests at:")
        print(f"https://webhook.site/#!/view/{token}")


if __name__ == "__main__":
    asyncio.run(main())
