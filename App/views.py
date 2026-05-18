from django.shortcuts import render, redirect
from django.db import transaction
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import IntegrityError
import re
from django.shortcuts import get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json
import asyncio
import edge_tts
import re
import google.generativeai as genai
from io import BytesIO
import tempfile
import os


def index(request):
	return render(request, 'index.html')


def signup_page(request):
	"""Render signup page and handle account creation with comprehensive validation.
	Validates: full name (no numbers), username (must contain letters), phone (10 digits),
	email format, password strength and match. Creates User and UserProfile atomically.
	"""
	if request.method == 'POST':
		full_name = request.POST.get('full_name', '').strip()
		username = request.POST.get('username', '').strip()
		email = request.POST.get('email', '').strip()
		phone = request.POST.get('phone', '').strip()
		password = request.POST.get('password', '')
		password_confirm = request.POST.get('password_confirm', '')

		errors = {}
		
		# Full name validation: required, no numbers
		if not full_name:
			errors['full_name'] = 'Full name is required.'
		elif re.search(r'\d', full_name):
			errors['full_name'] = 'Full name should not contain numbers.'
		
		# Username validation: required, must contain at least one letter (not only numbers)
		if not username:
			errors['username'] = 'Username is required.'
		elif not re.search(r'[a-zA-Z]', username):
			errors['username'] = 'Username must contain at least one letter.'
		elif User.objects.filter(username=username).exists():
			errors['username'] = 'This username is already taken.'
		
		# Email validation: required and valid format
		if not email:
			errors['email'] = 'Email is required.'
		else:
			try:
				validate_email(email)
				if User.objects.filter(email=email).exists():
					errors['email'] = 'An account with this email already exists.'
			except ValidationError:
				errors['email'] = 'Enter a valid email address.'
		
		# Phone validation: required, exactly 10 digits
		if not phone:
			errors['phone'] = 'Phone number is required.'
		elif not re.match(r'^\d{10}$', phone):
			errors['phone'] = 'Phone number must be exactly 10 digits.'
		
		# Password validation: required, min 8 chars, must match
		if not password:
			errors['password'] = 'Password is required.'
		elif len(password) < 8:
			errors['password'] = 'Password must be at least 8 characters.'
		
		if password != password_confirm:
			errors['password_confirm'] = 'Passwords do not match.'

		if errors:
			return render(request, 'signup.html', {'errors': errors, 'form': request.POST})

		# Create user and profile atomically
		from .models import UserProfile
		try:
			with transaction.atomic():
				user = User.objects.create_user(username=username, email=email, password=password)
				user.first_name = full_name
				user.save()
				
				UserProfile.objects.create(user=user, first_name=full_name, phone_number=phone)
		except IntegrityError:
			errors['general'] = 'Could not create account. Please try again.'
			return render(request, 'signup.html', {'errors': errors, 'form': request.POST})

		# Success - show success message
		return render(request, 'signup.html', {'success': True, 'username': username})

	return render(request, 'signup.html')


def login_page(request):
	"""Render login page and handle authentication.
	Validates username and password, returns error if invalid credentials.
	"""
	if request.method == 'POST':
		username = request.POST.get('username', '').strip()
		password = request.POST.get('password', '')
		
		errors = {}
		
		if not username:
			errors['username'] = 'Username is required.'
		if not password:
			errors['password'] = 'Password is required.'
		
		if not errors:
			user = authenticate(request, username=username, password=password)
			
			if user is not None:
				login(request, user)
				# Redirect admins to the admin dashboard, others to home page
				if user.is_staff or user.is_superuser:
					return redirect('admin_dashboard')
				return redirect('index')
			else:
				errors['general'] = 'Invalid username or password.'
		
		return render(request, 'login.html', {'errors': errors, 'form': request.POST})
	
	return render(request, 'login.html')


def logout_view(request):
	"""Log the user out and redirect to index."""
	logout(request)
	return redirect('index')


@login_required(login_url='/login/')
def speech(request):
	"""Render the speech analysis page. Requires authentication."""
	return render(request, 'speech.html')


@login_required(login_url='/login/')
def admin_dashboard(request):
	"""Render the admin dashboard.

	Provides minimal default context (stats, user_profile, notifications) so the
	template renders even if backend metrics are not yet implemented.
	"""
	from .models import UserProfile

	user = request.user

	# try to get profile, fallback to None
	try:
		user_profile = user.profile
	except (UserProfile.DoesNotExist, AttributeError):
		user_profile = None

	# Minimal stats; replace with real queries as needed
	stats = {
		'active_users': User.objects.filter(is_active=True).count(),
		'analyses': 0,
		'satisfaction': '94%'
	}

	# Minimal notifications placeholder
	notifications = []

	# Fetch users list for the admin table (exclude superusers for safety if desired)
	users_qs = User.objects.all().order_by('-date_joined')

	context = {
		'stats': stats,
		'user_profile': user_profile,
		'notifications': notifications,
		'users': users_qs,
		# keep user_state key used in some templates (empty if not available)
		'user_state': getattr(user_profile, 'state', '')
	}

	return render(request, 'admin_dashboard.html', context)


@login_required(login_url='/login/')
def admin_user_view(request, user_id):
	"""Simple admin user detail view."""
	# Basic permission: only staff can view user details here
	if not request.user.is_staff:
		return redirect('admin_dashboard')

	user_obj = get_object_or_404(User, id=user_id)
	# Try to get profile if available
	try:
		profile = user_obj.profile
	except Exception:
		profile = None

	return render(request, 'admin_user_view.html', {'target_user': user_obj, 'profile': profile})


@login_required(login_url='/login/')
def admin_user_edit(request, user_id):
	"""Placeholder admin user edit - redirects to Django admin change or returns simple form later."""
	if not request.user.is_staff:
		return redirect('admin_dashboard')

	# For now, redirect to Django admin change page if available
	try:
		return redirect(f'/admin/auth/user/{user_id}/change/')
	except Exception:
		messages.info(request, 'Edit via Django admin is not available.');
		return redirect('admin_dashboard')


@login_required(login_url='/login/')
def admin_user_delete(request, user_id):
	"""Delete a user (POST only)."""
	if not request.user.is_staff:
		return redirect('admin_dashboard')
	if request.method != 'POST':
		return redirect('admin_dashboard')

	user_obj = get_object_or_404(User, id=user_id)

	if user_obj == request.user:
		messages.error(request, "You cannot delete your own account from here.")
		return redirect('admin_dashboard')

	user_obj.delete()
	messages.success(request, f'User {user_obj.username} deleted.')
	return redirect('admin_dashboard')



@login_required(login_url='/login/')
def admin_user_api(request, user_id):
	"""Return JSON details for a user (admin use)."""
	if not request.user.is_staff:
		return JsonResponse({'success': False, 'error': 'permission_denied'}, status=403)

	user_obj = get_object_or_404(User, id=user_id)
	try:
		profile = user_obj.profile
	except Exception:
		profile = None

	data = {
		'id': user_obj.id,
		'username': user_obj.username,
		'email': user_obj.email,
		'first_name': user_obj.first_name,
		'last_name': user_obj.last_name,
		'is_staff': user_obj.is_staff,
		'is_superuser': user_obj.is_superuser,
		'date_joined': user_obj.date_joined.isoformat(),
		'profile': {
			'phone_number': getattr(profile, 'phone_number', ''),
			'state': getattr(profile, 'state', ''),
			'profile_picture': profile.profile_picture.url if getattr(profile, 'profile_picture', None) else ''
		}
	}

	return JsonResponse({'success': True, 'user': data})


@require_http_methods(['POST'])
@login_required(login_url='/login/')
def admin_user_update(request, user_id):
	"""Update editable user fields via JSON POST. Returns JSON."""
	if not request.user.is_staff:
		return JsonResponse({'success': False, 'error': 'permission_denied'}, status=403)

	user_obj = get_object_or_404(User, id=user_id)

	try:
		payload = json.loads(request.body.decode('utf-8'))
	except Exception:
		return JsonResponse({'success': False, 'error': 'invalid_json'}, status=400)

	# Allowed fields
	email = payload.get('email')
	first_name = payload.get('first_name')
	last_name = payload.get('last_name')
	is_staff = payload.get('is_staff')
	phone_number = payload.get('phone_number')
	state = payload.get('state')

	# Basic validation
	if email:
		try:
			validate_email(email)
			# ensure unique email if changed
			if User.objects.filter(email=email).exclude(id=user_obj.id).exists():
				return JsonResponse({'success': False, 'error': 'email_taken'}, status=400)
		except ValidationError:
			return JsonResponse({'success': False, 'error': 'invalid_email'}, status=400)

	# Apply changes
	if email is not None:
		user_obj.email = email
	if first_name is not None:
		user_obj.first_name = first_name
	if last_name is not None:
		user_obj.last_name = last_name
	if is_staff is not None:
		# ensure cannot remove own staff status
		if user_obj == request.user and not is_staff:
			return JsonResponse({'success': False, 'error': 'cannot_remove_own_staff'}, status=400)
		user_obj.is_staff = bool(is_staff)

	user_obj.save()

	# Profile handling
	from .models import UserProfile
	profile, created = UserProfile.objects.get_or_create(user=user_obj)
	if phone_number is not None:
		profile.phone_number = phone_number
	
	profile.save()

	return JsonResponse({'success': True, 'user': {
		'id': user_obj.id,
		'username': user_obj.username,
		'email': user_obj.email,
		'first_name': user_obj.first_name,
		'last_name': user_obj.last_name,
		'is_staff': user_obj.is_staff,
		'profile': {
			'phone_number': profile.phone_number,
			# 'state': profile.state
		}
	}})


# Configure Gemini API
GEMINI_API_KEY = "AIzaSyB_iLR8VZB6ZqO6_p3Dihqoyqjs3hx17hs"
genai.configure(api_key=GEMINI_API_KEY)

# Model names
PRIMARY_MODEL = "gemini-2.0-flash"
FALLBACK_MODEL = "gemini-2.5-flash-lite"


def correct_disfluent_speech(text, language='en'):
	"""Process disfluent speech to get fluent, corrected text.
	
	Handles:
	- Stuttering (e.g., "I-I-I want", "th-th-the")
	- Word/phrase repetitions (e.g., "I want I want to go")
	- Filler words (um, uh, like, you know, er, ah)
	- False starts and revisions
	- Prolongations
	- Interjections
	- Grammar errors
	
	Supports multiple languages: English, Hindi, Malayalam, Spanish.
	Uses Gemini API with fallback support.
	"""
	if not text or not text.strip():
		return text, text
	
	# First pass: Basic pattern-based cleanup for common disfluencies
	cleaned = preprocess_disfluencies(text, language)
	
	# Language-specific prompts for Gemini
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
	
	# Try primary model first
	try:
		model = genai.GenerativeModel(PRIMARY_MODEL)
		response = model.generate_content(prompt)
		corrected = response.text.strip()
		
		# Remove quotes if added
		corrected = strip_quotes(corrected)
		
		return cleaned, corrected
		
	except Exception as e:
		print(f"Primary model ({PRIMARY_MODEL}) failed: {str(e)}")
		
		# Try fallback model
		try:
			model = genai.GenerativeModel(FALLBACK_MODEL)
			response = model.generate_content(prompt)
			corrected = response.text.strip()
			corrected = strip_quotes(corrected)
			
			return cleaned, corrected
			
		except Exception as e2:
			print(f"Fallback model ({FALLBACK_MODEL}) also failed: {str(e2)}")
			# Return preprocessed text if API fails
			return cleaned, cleaned


def preprocess_disfluencies(text, language='en'):
	"""Basic pattern-based preprocessing for common disfluencies based on language."""
	import re
	
	# Normalize whitespace
	text = ' '.join(text.split())
	
	# Remove stuttering patterns: "I-I-I" -> "I", "th-th-the" -> "the"
	# Works for all languages with hyphenated stuttering
	text = re.sub(r'\b(\w+)(?:-\1)+\b', r'\1', text, flags=re.IGNORECASE)
	
	# Remove stuttering with partial: "b-b-but" -> "but"
	text = re.sub(r'\b(\w)-(?:\1-)*(\w+)\b', r'\1\2', text, flags=re.IGNORECASE)
	
	# Language-specific filler words
	if language == 'en':
		fillers = [
			r'\bum+\b', r'\buh+\b', r'\ber+\b', r'\bah+\b', r'\bmm+\b',
			r'\blike\b(?!\s+(?:a|the|this|that|to))',
			r'\byou know\b', r'\bi mean\b', r'\bbasically\b', r'\bactually\b',
			r'\bkind of\b', r'\bsort of\b', r'\bjust\b(?!\s+(?:now|then|like))',
			r'\bwell\b(?=\s*[,.]?\s*(?:i|you|we|they|he|she|it))',
			r'\bso\b(?=\s*[,.]?\s*(?:i|you|we|they|he|she|it|um|uh))'
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


def strip_quotes(text):
	"""Remove surrounding quotes from text."""
	if text.startswith('"') and text.endswith('"'):
		text = text[1:-1]
	if text.startswith("'") and text.endswith("'"):
		text = text[1:-1]
	return text


def correct_grammar_with_gemini(text):
	"""Correct grammar using Google Gemini API with fallback support.
	
	Tries primary model first, falls back to secondary if quota exceeded.
	"""
	if not text or not text.strip():
		return text
	
	prompt = f"""You are a grammar correction assistant. Correct any grammar, spelling, or punctuation mistakes in the following text. Return ONLY the corrected text without any explanations, quotes, or additional commentary.

Text: {text}

Corrected text:"""
	
	# Try primary model first
	try:
		model = genai.GenerativeModel(PRIMARY_MODEL)
		response = model.generate_content(prompt)
		corrected = response.text.strip()
		
		# Remove quotes if Gemini added them
		if corrected.startswith('"') and corrected.endswith('"'):
			corrected = corrected[1:-1]
		if corrected.startswith("'") and corrected.endswith("'"):
			corrected = corrected[1:-1]
		
		return corrected
		
	except Exception as e:
		print(f"Primary model ({PRIMARY_MODEL}) failed: {str(e)}")
		
		# Try fallback model
		try:
			model = genai.GenerativeModel(FALLBACK_MODEL)
			response = model.generate_content(prompt)
			corrected = response.text.strip()
			
			# Remove quotes if Gemini added them
			if corrected.startswith('"') and corrected.endswith('"'):
				corrected = corrected[1:-1]
			if corrected.startswith("'") and corrected.endswith("'"):
				corrected = corrected[1:-1]
			
			return corrected
			
		except Exception as e2:
			print(f"Fallback model ({FALLBACK_MODEL}) also failed: {str(e2)}")
			# Return original text if both models fail
			return text


def get_voice_for_language(lang_code='en', gender='female'):
	"""Get appropriate TTS voice based on language and gender."""
	voice_map = {
		'en': {
			'female': 'en-US-AriaNeural',
			'male': 'en-US-GuyNeural'
		},
		'hi': {
			'female': 'hi-IN-SwaraNeural',
			'male': 'hi-IN-MadhurNeural'
		},
		'ml': {
			'female': 'ml-IN-SobhanaNeural',
			'male': 'ml-IN-MidhunNeural'
		},
		'es': {
			'female': 'es-ES-ElviraNeural',
			'male': 'es-ES-AlvaroNeural'
		}
	}
	
	# Get voice, default to English female if not found
	return voice_map.get(lang_code, voice_map['en']).get(gender, voice_map['en']['female'])


@csrf_exempt
@require_http_methods(['POST'])
def process_speech_tts(request):
	"""Process disfluent speech: correct disfluencies and generate TTS audio.
	
	Handles stuttering, repetitions, filler words, and grammar issues.
	Supports multiple languages: English, Hindi, Malayalam, Spanish.
	Returns JSON with original, preprocessed, corrected text and audio.
	"""
	try:
		payload = json.loads(request.body.decode('utf-8'))
		text = payload.get('text', '').strip()
		lang = payload.get('language', 'en').strip()
		gender = payload.get('gender', 'female').strip()
		
		if not text:
			return JsonResponse({'success': False, 'error': 'No text provided'}, status=400)
		
		# Process disfluent speech using pattern matching + Gemini AI (with language support)
		preprocessed_text, corrected_text = correct_disfluent_speech(text, lang)
		
		# Check if there were any corrections
		has_corrections = (text.lower().strip() != corrected_text.lower().strip())
		
		# Get appropriate voice for the language and gender
		voice = get_voice_for_language(lang, gender)
		
		async def generate_audio(text_to_speak):
			"""Generate TTS audio using edge-tts."""
			communicate = edge_tts.Communicate(text_to_speak, voice)
			
			# Save to temporary file
			with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
				tmp_path = tmp_file.name
			
			await communicate.save(tmp_path)
			
			# Read the audio file
			with open(tmp_path, 'rb') as f:
				audio_data = f.read()
			
			# Clean up temp file
			os.unlink(tmp_path)
			
			return audio_data
		
		# Run async TTS generation
		loop = asyncio.new_event_loop()
		asyncio.set_event_loop(loop)
		
		# Generate audio for corrected fluent text (this is what we want to play back)
		corrected_audio = loop.run_until_complete(generate_audio(corrected_text))
		
		loop.close()
		
		# Encode audio as base64
		import base64
		corrected_audio_b64 = base64.b64encode(corrected_audio).decode('utf-8')
		
		# Calculate disfluency metrics
		original_words = len(text.split())
		corrected_words = len(corrected_text.split())
		disfluency_count = max(0, original_words - corrected_words)
		
		# Save to database if user is authenticated
		if request.user.is_authenticated:
			from .models import SpeechHistory
			SpeechHistory.objects.create(
				user=request.user,
				original_text=text,
				preprocessed_text=preprocessed_text,
				corrected_text=corrected_text,
				language=lang,
				gender=gender,
				has_corrections=has_corrections,
				original_word_count=original_words,
				corrected_word_count=corrected_words,
				disfluencies_removed=disfluency_count
			)
		
		return JsonResponse({
			'success': True,
			'original_text': text,
			'preprocessed_text': preprocessed_text,
			'corrected_text': corrected_text,
			'has_corrections': has_corrections,
			'corrected_audio': corrected_audio_b64,
			'metrics': {
				'original_word_count': original_words,
				'corrected_word_count': corrected_words,
				'disfluencies_removed': disfluency_count
			}
		})
		
	except Exception as e:
		import traceback
		traceback.print_exc()
		return JsonResponse({
			'success': False,
			'error': str(e)
		}, status=500)


@login_required(login_url='/login/')
def get_speech_history(request):
	"""Fetch speech analysis history for the logged-in user."""
	try:
		from .models import SpeechHistory
		
		# Get limit from query params (default 50)
		limit = int(request.GET.get('limit', 50))
		
		# Fetch user's speech history
		history = SpeechHistory.objects.filter(user=request.user)[:limit]
		
		# Format data
		history_data = []
		for entry in history:
			history_data.append({
				'id': entry.id,
				'original_text': entry.original_text,
				'preprocessed_text': entry.preprocessed_text,
				'corrected_text': entry.corrected_text,
				'language': entry.language,
				'gender': entry.gender,
				'has_corrections': entry.has_corrections,
				'original_word_count': entry.original_word_count,
				'corrected_word_count': entry.corrected_word_count,
				'disfluencies_removed': entry.disfluencies_removed,
				'created_at': entry.created_at.strftime('%Y-%m-%d %H:%M:%S')
			})
		
		return JsonResponse({
			'success': True,
			'history': history_data,
			'count': len(history_data)
		})
		
	except Exception as e:
		import traceback
		traceback.print_exc()
		return JsonResponse({
			'success': False,
			'error': str(e)
		}, status=500)


# ==================== CHAT ROOM API ====================

@login_required(login_url='/login/')
@require_http_methods(['POST'])
def create_chat_room(request):
	"""Create a new chat room."""
	try:
		from .models import ChatRoom, ChatRoomParticipant
		
		payload = json.loads(request.body.decode('utf-8'))
		room_name = payload.get('name', '').strip()
		language = payload.get('language', 'en').strip()
		
		if not room_name:
			return JsonResponse({'success': False, 'error': 'Room name is required'}, status=400)
		
		# Generate unique room code
		room_code = ChatRoom.generate_room_code()
		
		# Create room
		room = ChatRoom.objects.create(
			room_code=room_code,
			name=room_name,
			created_by=request.user,
			language=language
		)
		
		# Add creator as participant
		ChatRoomParticipant.objects.create(
			room=room,
			user=request.user,
			is_active=True
		)
		
		return JsonResponse({
			'success': True,
			'room': {
				'room_code': room.room_code,
				'name': room.name,
				'language': room.language,
				'created_by': request.user.username,
				'created_at': room.created_at.strftime('%Y-%m-%d %H:%M:%S')
			}
		})
		
	except Exception as e:
		import traceback
		traceback.print_exc()
		return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required(login_url='/login/')
@require_http_methods(['POST'])
def join_chat_room(request):
	"""Join an existing chat room by code."""
	try:
		from .models import ChatRoom, ChatRoomParticipant
		
		payload = json.loads(request.body.decode('utf-8'))
		room_code = payload.get('room_code', '').strip().upper()
		
		if not room_code:
			return JsonResponse({'success': False, 'error': 'Room code is required'}, status=400)
		
		try:
			room = ChatRoom.objects.get(room_code=room_code, is_active=True)
		except ChatRoom.DoesNotExist:
			return JsonResponse({'success': False, 'error': 'Room not found or inactive'}, status=404)
		
		# Add/reactivate participant
		participant, created = ChatRoomParticipant.objects.get_or_create(
			room=room,
			user=request.user,
			defaults={'is_active': True}
		)
		
		if not created:
			participant.is_active = True
			participant.save()
		
		return JsonResponse({
			'success': True,
			'room': {
				'room_code': room.room_code,
				'name': room.name,
				'language': room.language,
				'created_by': room.created_by.username,
				'participant_count': room.participants.filter(is_active=True).count()
			}
		})
		
	except Exception as e:
		import traceback
		traceback.print_exc()
		return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required(login_url='/login/')
def get_chat_room(request, room_code):
	"""Get chat room details."""
	try:
		from .models import ChatRoom, ChatRoomParticipant
		
		try:
			room = ChatRoom.objects.get(room_code=room_code.upper())
		except ChatRoom.DoesNotExist:
			return JsonResponse({'success': False, 'error': 'Room not found'}, status=404)
		
		participants = ChatRoomParticipant.objects.filter(room=room, is_active=True).select_related('user')
		
		return JsonResponse({
			'success': True,
			'room': {
				'room_code': room.room_code,
				'name': room.name,
				'language': room.language,
				'created_by': room.created_by.username,
				'created_at': room.created_at.strftime('%Y-%m-%d %H:%M:%S'),
				'is_active': room.is_active,
				'participants': [
					{
						'username': p.user.username,
						'joined_at': p.joined_at.strftime('%Y-%m-%d %H:%M:%S')
					}
					for p in participants
				],
				'participant_count': participants.count()
			}
		})
		
	except Exception as e:
		import traceback
		traceback.print_exc()
		return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required(login_url='/login/')
def get_user_rooms(request):
	"""Get all rooms the user is participating in."""
	try:
		from .models import ChatRoomParticipant
		
		participations = ChatRoomParticipant.objects.filter(
			user=request.user
		).select_related('room', 'room__created_by').order_by('-room__created_at')
		
		rooms = []
		for p in participations:
			room = p.room
			active_count = room.participants.filter(is_active=True).count()
			rooms.append({
				'room_code': room.room_code,
				'name': room.name,
				'language': room.language,
				'created_by': room.created_by.username,
				'is_active': room.is_active,
				'participant_count': active_count,
				'joined_at': p.joined_at.strftime('%Y-%m-%d %H:%M:%S')
			})
		
		return JsonResponse({
			'success': True,
			'rooms': rooms
		})
		
	except Exception as e:
		import traceback
		traceback.print_exc()
		return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required(login_url='/login/')
@require_http_methods(['POST'])
def leave_chat_room(request, room_code):
	"""Leave a chat room."""
	try:
		from .models import ChatRoom, ChatRoomParticipant
		
		try:
			room = ChatRoom.objects.get(room_code=room_code.upper())
		except ChatRoom.DoesNotExist:
			return JsonResponse({'success': False, 'error': 'Room not found'}, status=404)
		
		ChatRoomParticipant.objects.filter(room=room, user=request.user).update(is_active=False)
		
		return JsonResponse({'success': True, 'message': 'Left room successfully'})
		
	except Exception as e:
		import traceback
		traceback.print_exc()
		return JsonResponse({'success': False, 'error': str(e)}, status=500)




