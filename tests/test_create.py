"""Quick test of create_webhook output."""
import asyncio
from utils.http_client import WebhookHttpClient
from services.webhook_service import WebhookService

async def main():
    async with WebhookHttpClient() as client:
        ws = WebhookService(client)
        result = await ws.create()
        print("=== create_webhook returns ===")
        for key, value in result.data.items():
            val_str = str(value) if value else "None"
            if len(val_str) > 70:
                val_str = val_str[:70] + "..."
            print(f"  {key}: {val_str}")
        await ws.delete(result.data['token'])
        print("\nWebhook deleted")

if __name__ == "__main__":
    asyncio.run(main())
