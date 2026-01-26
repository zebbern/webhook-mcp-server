"""Quick script to create a webhook and get temp email."""
import asyncio
from utils.http_client import WebhookHttpClient
from services.webhook_service import WebhookService

async def main():
    async with WebhookHttpClient() as client:
        service = WebhookService(client)
        result = await service.create()
        token = result.data["token"]
        email_result = service.get_email(token)
        dns_result = service.get_dns(token)
        
        print("=" * 60)
        print("YOUR TEMPORARY WEBHOOK ENDPOINTS")
        print("=" * 60)
        print(f"Token:  {token}")
        print(f"URL:    {result.data['url']}")
        print(f"Email:  {email_result.data['email']}")
        print(f"DNS:    {dns_result.data['dns_domain']}")
        print("=" * 60)
        print("View incoming requests at:")
        print(f"https://webhook.site/#!/view/{token}")

if __name__ == "__main__":
    asyncio.run(main())
