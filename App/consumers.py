"""
WebSocket consumers for real-time chat with disfluency correction.
"""
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from asgiref.sync import sync_to_async


class ChatConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for chat room functionality with disfluency correction."""
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.room_code = self.scope['url_route']['kwargs']['room_code']
        self.room_group_name = f'chat_{self.room_code}'
        self.user = self.scope.get('user')
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Notify room of new participant
        if self.user and self.user.is_authenticated:
            await self.add_participant()
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'user_join',
                    'username': self.user.username,
                    'user_id': self.user.id
                }
            )
            
            # Send room info and recent messages
            room_info = await self.get_room_info()
            await self.send(text_data=json.dumps({
                'type': 'room_info',
                'room': room_info
            }))
            
            messages = await self.get_recent_messages()
            await self.send(text_data=json.dumps({
                'type': 'message_history',
                'messages': messages
            }))
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        if self.user and self.user.is_authenticated:
            await self.remove_participant()
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'user_leave',
                    'username': self.user.username,
                    'user_id': self.user.id
                }
            )
        
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(text_data)
            message_type = data.get('type', 'chat_message')
            
            if message_type == 'chat_message':
                await self.handle_chat_message(data)
            elif message_type == 'typing':
                await self.handle_typing(data)
            elif message_type == 'get_participants':
                participants = await self.get_participants()
                await self.send(text_data=json.dumps({
                    'type': 'participants_list',
                    'participants': participants
                }))
                
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON'
            }))
    
    async def handle_chat_message(self, data):
        """Process and broadcast a chat message with disfluency correction."""
        message = data.get('message', '').strip()
        language = data.get('language', 'en')
        
        if not message:
            return
        
        if not self.user or not self.user.is_authenticated:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'You must be logged in to send messages'
            }))
            return
        
        # Process disfluency correction
        corrected_message, has_corrections, disfluencies_removed = await self.correct_disfluency(message, language)
        
        # Save message to database
        saved_message = await self.save_message(message, corrected_message, has_corrections, disfluencies_removed, language)
        
        # Broadcast to room
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message_id': saved_message['id'],
                'username': self.user.username,
                'user_id': self.user.id,
                'original_message': message,
                'corrected_message': corrected_message,
                'has_corrections': has_corrections,
                'disfluencies_removed': disfluencies_removed,
                'language': language,
                'timestamp': saved_message['timestamp']
            }
        )
    
    async def handle_typing(self, data):
        """Handle typing indicator."""
        is_typing = data.get('is_typing', False)
        
        if self.user and self.user.is_authenticated:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'typing_indicator',
                    'username': self.user.username,
                    'user_id': self.user.id,
                    'is_typing': is_typing
                }
            )
    
    # Event handlers for group messages
    async def chat_message(self, event):
        """Send chat message to WebSocket."""
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message_id': event['message_id'],
            'username': event['username'],
            'user_id': event['user_id'],
            'original_message': event['original_message'],
            'corrected_message': event['corrected_message'],
            'has_corrections': event['has_corrections'],
            'disfluencies_removed': event['disfluencies_removed'],
            'language': event['language'],
            'timestamp': event['timestamp']
        }))
    
    async def user_join(self, event):
        """Send user join notification."""
        await self.send(text_data=json.dumps({
            'type': 'user_join',
            'username': event['username'],
            'user_id': event['user_id']
        }))
    
    async def user_leave(self, event):
        """Send user leave notification."""
        await self.send(text_data=json.dumps({
            'type': 'user_leave',
            'username': event['username'],
            'user_id': event['user_id']
        }))
    
    async def typing_indicator(self, event):
        """Send typing indicator."""
        # Don't send to the user who is typing
        if event['user_id'] != self.user.id:
            await self.send(text_data=json.dumps({
                'type': 'typing',
                'username': event['username'],
                'is_typing': event['is_typing']
            }))
    
    # Database operations
    @database_sync_to_async
    def get_room_info(self):
        """Get room information."""
        from .models import ChatRoom, ChatRoomParticipant
        
        try:
            room = ChatRoom.objects.get(room_code=self.room_code)
            participants = ChatRoomParticipant.objects.filter(room=room, is_active=True).select_related('user')
            
            return {
                'room_code': room.room_code,
                'name': room.name,
                'language': room.language,
                'created_by': room.created_by.username,
                'participants': [
                    {'username': p.user.username, 'user_id': p.user.id}
                    for p in participants
                ],
                'participant_count': participants.count()
            }
        except ChatRoom.DoesNotExist:
            return None
    
    @database_sync_to_async
    def get_recent_messages(self, limit=50):
        """Get recent messages from the room."""
        from .models import ChatRoom, ChatMessage
        
        try:
            room = ChatRoom.objects.get(room_code=self.room_code)
            messages = ChatMessage.objects.filter(room=room).select_related('user').order_by('-created_at')[:limit]
            
            return [
                {
                    'id': msg.id,
                    'username': msg.user.username,
                    'user_id': msg.user.id,
                    'original_message': msg.original_message,
                    'corrected_message': msg.corrected_message,
                    'has_corrections': msg.has_corrections,
                    'disfluencies_removed': msg.disfluencies_removed,
                    'language': msg.language,
                    'timestamp': msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
                }
                for msg in reversed(list(messages))
            ]
        except ChatRoom.DoesNotExist:
            return []
    
    @database_sync_to_async
    def add_participant(self):
        """Add user as participant in the room."""
        from .models import ChatRoom, ChatRoomParticipant
        
        try:
            room = ChatRoom.objects.get(room_code=self.room_code)
            participant, created = ChatRoomParticipant.objects.get_or_create(
                room=room,
                user=self.user,
                defaults={'is_active': True}
            )
            if not created:
                participant.is_active = True
                participant.save()
        except ChatRoom.DoesNotExist:
            pass
    
    @database_sync_to_async
    def remove_participant(self):
        """Mark participant as inactive."""
        from .models import ChatRoom, ChatRoomParticipant
        
        try:
            room = ChatRoom.objects.get(room_code=self.room_code)
            ChatRoomParticipant.objects.filter(room=room, user=self.user).update(is_active=False)
        except ChatRoom.DoesNotExist:
            pass
    
    @database_sync_to_async
    def save_message(self, original, corrected, has_corrections, disfluencies, language):
        """Save a chat message to the database."""
        from .models import ChatRoom, ChatMessage
        
        room = ChatRoom.objects.get(room_code=self.room_code)
        message = ChatMessage.objects.create(
            room=room,
            user=self.user,
            original_message=original,
            corrected_message=corrected,
            has_corrections=has_corrections,
            disfluencies_removed=disfluencies,
            language=language
        )
        
        return {
            'id': message.id,
            'timestamp': message.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }
    
    @database_sync_to_async
    def get_participants(self):
        """Get current participant list."""
        from .models import ChatRoom, ChatRoomParticipant
        
        try:
            room = ChatRoom.objects.get(room_code=self.room_code)
            participants = ChatRoomParticipant.objects.filter(room=room, is_active=True).select_related('user')
            
            return [
                {'username': p.user.username, 'user_id': p.user.id}
                for p in participants
            ]
        except ChatRoom.DoesNotExist:
            return []
    
    @database_sync_to_async
    def correct_disfluency(self, text, language='en'):
        """Correct disfluencies in text using the same logic as speech processing."""
        import re
        import google.generativeai as genai
        
        if not text or not text.strip():
            return text, False, 0
        
        # Configure Gemini
        GEMINI_API_KEY = "AIzaSyB_iLR8VZB6ZqO6_p3Dihqoyqjs3hx17hs"
        genai.configure(api_key=GEMINI_API_KEY)
        
        PRIMARY_MODEL = "gemini-2.0-flash"
        FALLBACK_MODEL = "gemini-2.5-flash-lite"
        
        # First pass: Basic pattern-based cleanup
        cleaned = self.preprocess_text(text, language)
        
        # Language-specific prompts (same as views.py)
        language_instructions = {
            'en': """You are a speech-language pathologist assistant specializing in disfluent speech correction for ENGLISH.

The following text is from a person with speech disfluency (stuttering, stammering). Your task is to:
1. Remove ALL stuttering patterns (like "I-I-I", "th-th-the", "b-b-but")
2. Remove ALL filler words (um, uh, er, ah, like, you know, basically, actually, I mean)
3. Remove word/phrase repetitions (e.g., "I want I want" → "I want")
4. Fix false starts and revisions (e.g., "I went to the- I mean I drove to" → "I drove to")
5. Remove prolongations (e.g., "soooo" → "so", "aaand" → "and")
6. Fix any grammar issues
7. Make the sentence fluent and natural in English""",
            
            'hi': """आप एक भाषण-भाषा रोगविज्ञानी सहायक हैं जो हिंदी में अस्खलित भाषण सुधार में विशेषज्ञता रखते हैं।

You are a speech-language pathologist assistant specializing in disfluent speech correction for HINDI (हिंदी).

The following text is from a Hindi speaker with speech disfluency (stuttering/हकलाना). Your task is to:
1. Remove ALL stuttering patterns (like "म-म-मैं", "क-क-कैसे", "य-य-यह")
2. Remove ALL Hindi filler words (अं, उं, हां, वो, मतलब, बस, तो, ना, अच्छा, देखो, सुनो, basically, actually)
3. Remove word/phrase repetitions (e.g., "मैं मैं जाना चाहता हूं" → "मैं जाना चाहता हूं")
4. Fix false starts and revisions
5. Remove prolongations (e.g., "मैंंंं" → "मैं", "क्याааа" → "क्या")
6. Fix any grammar issues in Hindi
7. Make the sentence fluent and natural in Hindi
8. Keep the response in Hindi/Devanagari script""",
            
            'ml': """You are a speech-language pathologist assistant specializing in disfluent speech correction for MALAYALAM (മലയാളം).

The following text is from a Malayalam speaker with speech disfluency (stuttering). Your task is to:
1. Remove ALL stuttering patterns
2. Remove ALL Malayalam filler words (അത്, ഇത്, പിന്നെ, അല്ലേ, എന്താ, etc.)
3. Remove word/phrase repetitions
4. Fix false starts and revisions
5. Remove prolongations
6. Fix any grammar issues in Malayalam
7. Make the sentence fluent and natural in Malayalam
8. Keep the response in Malayalam script""",
            
            'es': """You are a speech-language pathologist assistant specializing in disfluent speech correction for SPANISH (Español).

The following text is from a Spanish speaker with speech disfluency (stuttering/tartamudeo). Your task is to:
1. Remove ALL stuttering patterns (like "y-y-yo", "e-e-el", "p-p-pero")
2. Remove ALL Spanish filler words (eh, este, pues, bueno, o sea, como que, entonces, mira, sabes)
3. Remove word/phrase repetitions (e.g., "yo yo quiero" → "yo quiero")
4. Fix false starts and revisions
5. Remove prolongations (e.g., "yoooo" → "yo")
6. Fix any grammar issues in Spanish
7. Make the sentence fluent and natural in Spanish"""
        }
        
        instruction = language_instructions.get(language, language_instructions['en'])
        
        prompt = f"""{instruction}

IMPORTANT: Return ONLY the corrected fluent sentence in the SAME language as the input. No explanations, no quotes, no commentary, no translations.

Disfluent text: {cleaned}

Fluent corrected text:"""
        
        corrected = cleaned
        
        # Try primary model first
        try:
            model = genai.GenerativeModel(PRIMARY_MODEL)
            response = model.generate_content(prompt)
            corrected = response.text.strip()
            
            # Remove quotes if added
            if corrected.startswith('"') and corrected.endswith('"'):
                corrected = corrected[1:-1]
            if corrected.startswith("'") and corrected.endswith("'"):
                corrected = corrected[1:-1]
                
        except Exception as e:
            print(f"Primary model ({PRIMARY_MODEL}) failed: {str(e)}")
            
            # Try fallback model
            try:
                model = genai.GenerativeModel(FALLBACK_MODEL)
                response = model.generate_content(prompt)
                corrected = response.text.strip()
                
                if corrected.startswith('"') and corrected.endswith('"'):
                    corrected = corrected[1:-1]
                if corrected.startswith("'") and corrected.endswith("'"):
                    corrected = corrected[1:-1]
                    
            except Exception as e2:
                print(f"Fallback model ({FALLBACK_MODEL}) also failed: {str(e2)}")
                corrected = cleaned
        
        # Calculate metrics
        has_corrections = text.lower().strip() != corrected.lower().strip()
        original_words = len(text.split())
        corrected_words = len(corrected.split())
        disfluencies = max(0, original_words - corrected_words)
        
        return corrected, has_corrections, disfluencies
    
    def preprocess_text(self, text, language='en'):
        """Basic pattern-based preprocessing for disfluencies."""
        import re
        
        # Normalize whitespace
        text = ' '.join(text.split())
        
        # Remove stuttering patterns: "I-I-I" -> "I", "th-th-the" -> "the"
        text = re.sub(r'\b(\w+)(?:-\1)+\b', r'\1', text, flags=re.IGNORECASE)
        
        # Remove stuttering with partial: "b-b-but" -> "but"
        text = re.sub(r'\b(\w)-(?:\1-)*(\w+)\b', r'\1\2', text, flags=re.IGNORECASE)
        
        # Language-specific filler words
        if language == 'en':
            fillers = [
                r'\bum+\b', r'\buh+\b', r'\ber+\b', r'\bah+\b', r'\bmm+\b',
                r'\blike\b(?!\s+(?:a|the|this|that|to))',
                r'\byou know\b', r'\bi mean\b', r'\bbasically\b', r'\bactually\b',
                r'\bkind of\b', r'\bsort of\b'
            ]
        elif language == 'hi':
            fillers = [
                r'\bअं+\b', r'\bउं+\b', r'\bहां+\b', r'\bवो\b', r'\bमतलब\b',
                r'\bबस\b(?!\s+(?:स्टॉप|स्टैंड))', r'\bतो\b', r'\bना\b(?=\s)',
                r'\bअच्छा\b(?=\s*[,.]?\s*(?:तो|और|मैं|आप|वो|यह))',
                r'\bदेखो\b', r'\bसुनो\b', r'\bbasically\b', r'\bactually\b',
                r'\blike\b', r'\bum+\b', r'\buh+\b'
            ]
        elif language == 'ml':
            fillers = [
                r'\bഅത്\b', r'\bഇത്\b', r'\bപിന്നെ\b', r'\bഅല്ലേ\b',
                r'\bഎന്താ\b(?=\s)', r'\bum+\b', r'\buh+\b'
            ]
        elif language == 'es':
            fillers = [
                r'\beh+\b', r'\beste\b', r'\bpues\b', r'\bbueno\b(?=\s*[,.]?\s*(?:yo|tu|el|ella))',
                r'\bo sea\b', r'\bcomo que\b', r'\bentonces\b(?=\s*[,.]?\s*(?:yo|tu))',
                r'\bmira\b(?=\s*[,.])', r'\bsabes\b(?=\s*[,.])'
            ]
        else:
            fillers = [r'\bum+\b', r'\buh+\b', r'\ber+\b', r'\bah+\b']
        
        for filler in fillers:
            text = re.sub(filler, '', text, flags=re.IGNORECASE)
        
        # Remove prolongations: "soooo" -> "so", "nooo" -> "no"
        text = re.sub(r'\b(\w)(\1{2,})', r'\1', text)
        text = re.sub(r'(\w)\1{3,}', r'\1\1', text)
        
        # Remove immediate word repetitions: "I I want" -> "I want"
        text = re.sub(r'\b(\w+)(\s+\1)+\b', r'\1', text, flags=re.IGNORECASE)
        text = re.sub(r'\b(\w+)(\s+\1)+\b', r'\1', text, flags=re.IGNORECASE)
        
        # Clean up multiple spaces and punctuation
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\s+([,.])', r'\1', text)
        text = re.sub(r'([,.])\s*\1+', r'\1', text)
        
        return text.strip()
