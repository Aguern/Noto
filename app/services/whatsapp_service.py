"""WhatsApp Business API service"""
import os
import json
import aiofiles
from typing import Dict, Optional, List, Any
from datetime import datetime
from pathlib import Path
import httpx
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


class WhatsAppService:
    """Service for WhatsApp Business API interactions"""
    
    def __init__(self):
        self.token = os.getenv("WHATSAPP_TOKEN")
        self.phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        self.verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN")
        self.business_account_id = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")
        
        # API endpoints
        self.base_url = "https://graph.facebook.com/v18.0"
        self.messages_url = f"{self.base_url}/{self.phone_number_id}/messages"
        self.media_url = f"{self.base_url}/{self.phone_number_id}/media"
        
        # Configuration
        self.max_message_length = int(os.getenv("WHATSAPP_MAX_MESSAGE_LENGTH", "1600"))
        
        # Headers for API requests
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
        # Track message statistics
        self._messages_sent = 0
        self._api_calls = 0
    
    async def send_text(
        self,
        to: str,
        text: str,
        preview_url: bool = False
    ) -> Dict:
        """Alias for send_text_message for consistency"""
        return await self.send_text_message(to, text, preview_url)
    
    async def send_text_message(
        self,
        to: str,
        text: str,
        preview_url: bool = False
    ) -> Dict:
        """
        Send text message via WhatsApp Business API
        
        Args:
            to: Recipient phone number
            text: Message text
            preview_url: Whether to preview URLs in the message
            
        Returns:
            API response dict
        """
        # Truncate message if too long
        if len(text) > self.max_message_length:
            text = text[:self.max_message_length-10] + "...[tronqué]"
            logger.warning(f"Message truncated to {self.max_message_length} characters")
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {
                "body": text,
                "preview_url": preview_url
            }
        }
        
        return await self._make_api_request("POST", self.messages_url, payload)
    
    async def send_audio(
        self,
        to: str,
        file_path_or_url: str,
        caption: Optional[str] = None
    ) -> Dict:
        """Send audio via path or URL"""
        # Check if it's a URL or file path
        if file_path_or_url.startswith("http"):
            # It's a URL - would need to download first or send as link
            # For now, treat as error
            logger.warning("Audio URLs not yet supported, use file path")
            return {"error": "Audio URLs not yet supported"}
        else:
            return await self.send_audio_message(to, file_path_or_url, caption)
    
    async def send_audio_message(
        self,
        to: str,
        audio_path: str,
        caption: Optional[str] = None
    ) -> Dict:
        """
        Send audio message via WhatsApp Business API
        
        Args:
            to: Recipient phone number
            audio_path: Path to audio file
            caption: Optional audio caption
            
        Returns:
            API response dict
        """
        try:
            # Upload audio to WhatsApp servers first
            media_id = await self._upload_media(audio_path, "audio")
            
            if not media_id:
                raise Exception("Failed to upload audio file")
            
            # Send audio message
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "audio",
                "audio": {
                    "id": media_id
                }
            }
            
            if caption:
                payload["audio"]["caption"] = caption
            
            return await self._make_api_request("POST", self.messages_url, payload)
            
        except Exception as e:
            logger.error(f"Failed to send audio message: {e}")
            return {"error": str(e)}
    
    async def send_message_with_audio(
        self,
        to: str,
        text: str,
        audio_path: Optional[str] = None
    ) -> List[Dict]:
        """
        Send text message followed by audio message
        
        Args:
            to: Recipient phone number
            text: Text message content
            audio_path: Optional path to audio file
            
        Returns:
            List of API responses
        """
        responses = []
        
        # Send text message
        text_response = await self.send_text_message(to, text)
        responses.append(text_response)
        
        # Send audio if provided
        if audio_path and os.path.exists(audio_path):
            audio_response = await self.send_audio_message(to, audio_path)
            responses.append(audio_response)
        
        return responses
    
    async def send_template_message(
        self,
        to: str,
        template_name: str,
        language_code: str = "fr",
        parameters: Optional[List[str]] = None
    ) -> Dict:
        """
        Send WhatsApp template message
        
        Args:
            to: Recipient phone number
            template_name: Name of approved template
            language_code: Language code
            parameters: Template parameters
            
        Returns:
            API response dict
        """
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "code": language_code
                }
            }
        }
        
        # Add parameters if provided
        if parameters:
            payload["template"]["components"] = [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": param} for param in parameters
                    ]
                }
            ]
        
        return await self._make_api_request("POST", self.messages_url, payload)
    
    async def download_media(
        self,
        media_id: str,
        save_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Download media from WhatsApp
        
        Args:
            media_id: Media ID from WhatsApp
            save_path: Path to save the file
            
        Returns:
            Path to downloaded file, or None if failed
        """
        try:
            # Get media URL
            media_info_url = f"{self.base_url}/{media_id}"
            
            async with httpx.AsyncClient() as client:
                # Get media info
                response = await client.get(
                    media_info_url,
                    headers={"Authorization": f"Bearer {self.token}"}
                )
                response.raise_for_status()
                media_info = response.json()
                
                # Download media file
                media_url = media_info["url"]
                media_response = await client.get(
                    media_url,
                    headers={"Authorization": f"Bearer {self.token}"}
                )
                media_response.raise_for_status()
                
                # Determine file extension
                mime_type = media_info.get("mime_type", "")
                extension = self._get_extension_from_mime(mime_type)
                
                # Save file
                if not save_path:
                    save_path = f"downloads/{media_id}{extension}"
                
                Path(save_path).parent.mkdir(parents=True, exist_ok=True)
                
                async with aiofiles.open(save_path, "wb") as f:
                    await f.write(media_response.content)
                
                logger.info(f"Media downloaded: {save_path}")
                return save_path
        
        except Exception as e:
            logger.error(f"Failed to download media {media_id}: {e}")
            return None
    
    async def _upload_media(self, file_path: str, media_type: str) -> Optional[str]:
        """Upload media file to WhatsApp servers"""
        try:
            # Prepare file upload
            async with aiofiles.open(file_path, "rb") as f:
                file_content = await f.read()
            
            # Determine MIME type
            file_extension = Path(file_path).suffix.lower()
            mime_type = self._get_mime_type(file_extension)
            
            files = {
                "file": (Path(file_path).name, file_content, mime_type),
                "type": (None, media_type),
                "messaging_product": (None, "whatsapp")
            }
            
            # Upload file
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.media_url,
                    files=files,
                    headers={"Authorization": f"Bearer {self.token}"}
                )
                response.raise_for_status()
                
                result = response.json()
                media_id = result.get("id")
                
                if media_id:
                    logger.info(f"Media uploaded successfully: {media_id}")
                    return media_id
                else:
                    logger.error(f"No media ID in response: {result}")
                    return None
        
        except Exception as e:
            logger.error(f"Media upload failed: {e}")
            return None
    
    async def _make_api_request(
        self,
        method: str,
        url: str,
        payload: Optional[Dict] = None
    ) -> Dict:
        """Make authenticated API request to WhatsApp"""
        try:
            self._api_calls += 1
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                if method.upper() == "POST":
                    response = await client.post(
                        url,
                        json=payload,
                        headers=self.headers
                    )
                elif method.upper() == "GET":
                    response = await client.get(
                        url,
                        headers=self.headers
                    )
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                response.raise_for_status()
                result = response.json()
                
                # Track successful messages
                if "messages" in result and result.get("messages"):
                    self._messages_sent += len(result["messages"])
                
                logger.info(f"WhatsApp API call successful: {method} {url}")
                return result
        
        except httpx.HTTPStatusError as e:
            error_detail = ""
            try:
                error_response = e.response.json()
                error_detail = error_response.get("error", {}).get("message", "")
            except:
                error_detail = e.response.text
            
            logger.error(f"WhatsApp API error ({e.response.status_code}): {error_detail}")
            return {
                "error": f"HTTP {e.response.status_code}",
                "detail": error_detail
            }
        
        except Exception as e:
            logger.error(f"WhatsApp API request failed: {e}")
            return {"error": str(e)}
    
    def _get_mime_type(self, extension: str) -> str:
        """Get MIME type from file extension"""
        mime_types = {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".ogg": "audio/ogg",
            ".m4a": "audio/mp4",
            ".aac": "audio/aac",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".mp4": "video/mp4",
            ".mov": "video/quicktime",
            ".pdf": "application/pdf"
        }
        
        return mime_types.get(extension, "application/octet-stream")
    
    def _get_extension_from_mime(self, mime_type: str) -> str:
        """Get file extension from MIME type"""
        extensions = {
            "audio/mpeg": ".mp3",
            "audio/wav": ".wav",
            "audio/ogg": ".ogg",
            "audio/mp4": ".m4a",
            "audio/aac": ".aac",
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "video/mp4": ".mp4",
            "video/quicktime": ".mov",
            "application/pdf": ".pdf"
        }
        
        return extensions.get(mime_type, "")
    
    def verify_webhook(
        self,
        mode: str,
        token: str,
        challenge: str
    ) -> Optional[str]:
        """
        Verify WhatsApp webhook
        
        Args:
            mode: Hub mode from webhook verification
            token: Verify token from webhook
            challenge: Challenge string from webhook
            
        Returns:
            Challenge string if verification successful, None otherwise
        """
        if mode == "subscribe" and token == self.verify_token:
            logger.info("Webhook verification successful")
            return challenge
        else:
            logger.warning(f"Webhook verification failed: mode={mode}, token_match={token == self.verify_token}")
            return None
    
    def get_statistics(self) -> Dict:
        """Get service statistics"""
        return {
            "messages_sent": self._messages_sent,
            "api_calls_made": self._api_calls,
            "phone_number_id": self.phone_number_id,
            "business_account_id": self.business_account_id
        }
    
    async def health_check(self) -> Dict:
        """Check WhatsApp Business API health"""
        try:
            # Test API connectivity with a simple request
            profile_url = f"{self.base_url}/{self.phone_number_id}"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    profile_url,
                    headers={"Authorization": f"Bearer {self.token}"}
                )
                response.raise_for_status()
                
                return {
                    "status": "healthy",
                    "api_accessible": True,
                    "phone_number_id": self.phone_number_id
                }
        
        except Exception as e:
            return {
                "status": "unhealthy",
                "api_accessible": False,
                "error": str(e)
            }