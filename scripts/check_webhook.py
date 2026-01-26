"""Check for incoming requests."""
import asyncio
import re
from utils.http_client import WebhookHttpClient
from services.request_service import RequestService

async def main():
    token = "16f47397-67a2-483e-9d89-0eec852ef21f"
    async with WebhookHttpClient() as client:
        service = RequestService(client)
        result = await service.get_all(token, limit=1)
        
        if result.data.get("requests"):
            content = result.data["requests"][0].get("content", "")
            
            # Find magic link - decode quoted-printable
            # Replace =3D with = and remove soft line breaks
            decoded = content.replace("=3D", "=").replace("=\r\n", "").replace("=\n", "")
            
            # Find the magic link
            match = re.search(r'https://blink\.new/auth\?magic_token=([a-f0-9]+)&email=([^\s"<>]+)', decoded)
            if match:
                print("MAGIC LINK FOUND:")
                print(f"https://blink.new/auth?magic_token={match.group(1)}&email={match.group(2)}")
            else:
                print("No magic link found")
                print("Looking for partial matches...")
                matches = re.findall(r'magic_token[^\s"<>]+', decoded)
                for m in matches[:3]:
                    print(m)

if __name__ == "__main__":
    asyncio.run(main())
