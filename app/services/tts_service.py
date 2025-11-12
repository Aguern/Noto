"""Clean TTS service with XTTS-v2 and macOS fallback"""
import os
import hashlib
import asyncio
from typing import Optional, Dict
from datetime import datetime
from pathlib import Path
import re
from loguru import logger
from dotenv import load_dotenv

# Fix PyTorch 2.8 compatibility for XTTS-v2
os.environ['TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD'] = '1'

# Import TTS with fix
try:
    from TTS.api import TTS
    TTS_AVAILABLE = True
    logger.info("XTTS-v2 available with PyTorch 2.8 compatibility fix")
except ImportError as e:
    TTS_AVAILABLE = False
    logger.warning(f"TTS library not available: {e} - using macOS native synthesis")

load_dotenv()


class TTSService:
    """Clean TTS service with XTTS-v2 and macOS fallback"""
    
    def __init__(self):
        self.cache_dir = Path(os.getenv("TTS_CACHE_DIR", "cache/audio"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Strategy: Try XTTS-v2 first, fallback to macOS
        self.use_xtts = TTS_AVAILABLE
        self.use_macos_fallback = True
        
        # XTTS-v2 config
        if self.use_xtts:
            self.model_name = "tts_models/multilingual/multi-dataset/xtts_v2"
            self.default_voice = "voices/nicolas_voice.wav"
            self.tts = None
            self.model_loaded = False
        
        # macOS config
        self.macos_voice = "Thomas"
        self.speech_rate = 180
        
        logger.info(f"Clean TTS initialized - XTTS: {self.use_xtts}")
    
    def _preprocess_french_text(self, text: str) -> str:
        """Optimize text for French TTS"""
        # Years
        text = re.sub(r'\b2025\b', 'deux mille vingt-cinq', text)
        text = re.sub(r'\b2024\b', 'deux mille vingt-six', text)
        
        # Abbreviations
        abbrevs = {
            'OM': 'Olympique de Marseille', 'PSG': 'Paris Saint-Germain',
            'UE': 'Union Européenne', 'USA': 'États-Unis'
        }
        
        for abbr, full in abbrevs.items():
            text = re.sub(rf'\b{abbr}\b', full, text)
        
        # Natural pauses
        text = re.sub(r'(Côté \w+)', r'\1,', text)
        text = re.sub(r'(Pour l[ae] \w+)', r'\1,', text)
        text = re.sub(r'(Enfin pour \w+)', r'\1,', text)
        
        return text.strip()
    
    async def _load_xtts_model(self):
        """Load XTTS-v2 model"""
        if self.model_loaded or not TTS_AVAILABLE:
            return
        
        try:
            logger.info("Loading XTTS-v2 model...")
            loop = asyncio.get_event_loop()
            
            def _load():
                tts = TTS(self.model_name, gpu=False)
                return tts
            
            self.tts = await loop.run_in_executor(None, _load)
            self.model_loaded = True
            
            logger.info("XTTS-v2 model loaded successfully")
            
        except Exception as e:
            logger.error(f"XTTS-v2 loading failed: {e}")
            self.use_xtts = False
    
    async def _try_xtts_synthesis(self, text: str, language: str, output_format: str) -> Optional[str]:
        """Try XTTS-v2 synthesis"""
        try:
            if not self.model_loaded:
                await self._load_xtts_model()
            
            if not self.model_loaded:
                return None
            
            # Preprocess text
            if language == "fr":
                text = self._preprocess_french_text(text)
            
            # Generate cache key
            cache_key = hashlib.md5(f"{text}_{language}_xtts".encode()).hexdigest()
            cached_file = self.cache_dir / f"{cache_key}.{output_format}"
            
            # Return cached if exists
            if cached_file.exists():
                logger.info(f"Using cached XTTS audio: {cached_file}")
                return str(cached_file)
            
            # Generate audio
            temp_wav = self.cache_dir / f"{cache_key}_temp.wav"
            
            logger.info("Generating XTTS-v2 audio...")
            loop = asyncio.get_event_loop()
            
            def _generate():
                self.tts.tts_to_file(
                    text=text,
                    speaker_wav=self.default_voice,
                    language=language,
                    file_path=str(temp_wav)
                )
            
            await loop.run_in_executor(None, _generate)
            
            # Convert if needed
            if output_format == "mp3" and temp_wav.exists():
                convert_cmd = f'ffmpeg -i {temp_wav} -codec:a libmp3lame -b:a 192k {cached_file} -y 2>/dev/null'
                
                process = await asyncio.create_subprocess_shell(convert_cmd)
                await process.communicate()
                
                temp_wav.unlink()
            else:
                import shutil
                shutil.move(str(temp_wav), str(cached_file))
            
            logger.info(f"XTTS-v2 audio generated: {cached_file}")
            return str(cached_file)
            
        except Exception as e:
            logger.error(f"XTTS-v2 synthesis failed: {e}")
            return None
    
    async def _macos_synthesis(self, text: str, language: str, output_format: str) -> Optional[str]:
        """macOS native TTS synthesis"""
        try:
            # Preprocess
            if language == "fr":
                text = self._preprocess_french_text(text)
            
            # Cache key
            cache_key = hashlib.md5(f"{text}_{language}_macos".encode()).hexdigest()
            cached_file = self.cache_dir / f"{cache_key}.{output_format}"
            
            if cached_file.exists():
                logger.info(f"Using cached macOS audio: {cached_file}")
                return str(cached_file)
            
            # Generate with macOS
            temp_aiff = self.cache_dir / f"{cache_key}_temp.aiff"
            
            escaped_text = text.replace('"', '\\"').replace("'", "\\'")
            cmd = f'say -v "{self.macos_voice}" -r {self.speech_rate} "{escaped_text}" -o {temp_aiff}'
            
            process = await asyncio.create_subprocess_shell(cmd)
            await process.communicate()
            
            # Convert to desired format
            if output_format == "mp3":
                convert_cmd = f'ffmpeg -i {temp_aiff} -ar 24000 -codec:a libmp3lame -b:a 192k {cached_file} -y 2>/dev/null'
                process = await asyncio.create_subprocess_shell(convert_cmd)
                await process.communicate()
            else:
                import shutil
                shutil.move(str(temp_aiff), str(cached_file))
            
            # Cleanup
            if temp_aiff.exists():
                temp_aiff.unlink()
            
            logger.info(f"macOS audio generated: {cached_file}")
            return str(cached_file)
            
        except Exception as e:
            logger.error(f"macOS synthesis failed: {e}")
            return None
    
    async def text_to_speech(
        self,
        text: str,
        voice_profile_path: Optional[str] = None,
        language: str = "fr",
        output_format: str = "mp3"
    ) -> Optional[str]:
        """
        Generate speech from text using XTTS-v2 with macOS fallback
        """
        # Try XTTS first if available
        if self.use_xtts and TTS_AVAILABLE:
            result = await self._try_xtts_synthesis(text, language, output_format)
            if result:
                return result
            logger.warning("XTTS-v2 failed, falling back to macOS")
        
        # macOS fallback
        return await self._macos_synthesis(text, language, output_format)
    
    async def health_check(self) -> Dict:
        """Check TTS service health"""
        return {
            "service": "Clean TTS (XTTS-v2 + macOS)",
            "xtts_available": self.use_xtts and self.model_loaded,
            "macos_voice": self.macos_voice,
            "cache_dir": str(self.cache_dir)
        }