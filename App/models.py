from django.db import models
from django.contrib.auth.models import User
import uuid


class UserProfile(models.Model):
    """Extended user profile with additional information."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    first_name = models.CharField(max_length=150, blank=True)
    phone_number = models.CharField(max_length=30, blank=True)
    
    def __str__(self):
        return f"Profile for {self.user.username}"


class SpeechHistory(models.Model):
    """Store speech analysis history with disfluency corrections."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='speech_history')
    original_text = models.TextField(help_text="Original disfluent speech text")
    preprocessed_text = models.TextField(help_text="Text after pattern-based preprocessing")
    corrected_text = models.TextField(help_text="Final fluent corrected text")
    language = models.CharField(max_length=10, default='en', help_text="Language code (en, hi, ml, es)")
    gender = models.CharField(max_length=10, default='female', help_text="Voice gender")
    has_corrections = models.BooleanField(default=False, help_text="Whether disfluencies were found and corrected")
    original_word_count = models.IntegerField(default=0)
    corrected_word_count = models.IntegerField(default=0)
    disfluencies_removed = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Speech History'
        verbose_name_plural = 'Speech Histories'
    
    def __str__(self):
        return f"{self.user.username} - {self.created_at.strftime('%Y-%m-%d %H:%M')} - {self.language}"


class ChatRoom(models.Model):
    """Chat room for real-time messaging with disfluency support."""
    room_code = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_rooms')
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    max_participants = models.IntegerField(default=10)
    language = models.CharField(max_length=10, default='en', help_text="Default language for disfluency correction")
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.room_code})"
    
    @classmethod
    def generate_room_code(cls):
        """Generate a unique 6-character room code."""
        while True:
            code = uuid.uuid4().hex[:6].upper()
            if not cls.objects.filter(room_code=code).exists():
                return code


class ChatRoomParticipant(models.Model):
    """Track participants in a chat room."""
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_rooms')
    joined_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['room', 'user']
        ordering = ['joined_at']
    
    def __str__(self):
        return f"{self.user.username} in {self.room.name}"


class ChatMessage(models.Model):
    """Store chat messages with disfluency correction."""
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_messages')
    original_message = models.TextField(help_text="Original message (may contain disfluencies)")
    corrected_message = models.TextField(help_text="Corrected fluent message")
    has_corrections = models.BooleanField(default=False)
    disfluencies_removed = models.IntegerField(default=0)
    language = models.CharField(max_length=10, default='en')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.user.username}: {self.corrected_message[:50]}"
