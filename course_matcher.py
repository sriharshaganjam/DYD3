import json
import os
import openai
from dotenv import load_dotenv
import re
from difflib import SequenceMatcher

# (No changes needed in this section)
try:
    from embedding_matcher import get_enhanced_recommendations
    FAISS_AVAILABLE = True
    print("✅ FAISS embeddings system loaded successfully!")
except ImportError as e:
    FAISS_AVAILABLE = False
    print(f"⚠️ FAISS not available: {e}. Using fallback keyword matching.")

load_dotenv()
openai.api_key = os.getenv("MISTRAL_API_KEY")
openai.api_base = "https://api.mistral.ai/v1"

def load_courses(path="courses.json"):
    with open(path, "r") as f:
        return json.load(f)

def get_smart_course_recommendations(profile, courses, chat_history=[]):
    if FAISS_AVAILABLE:
        try:
            recommended_courses, _ = get_enhanced_recommendations(profile, courses, chat_history)
            return recommended_courses
        except Exception as e:
            print(f"⚠️ FAISS failed, using fallback: {e}")
            return filter_and_match_courses_fallback(courses, profile)
    else:
        return filter_and_match_courses_fallback(courses, profile)

def filter_and_match_courses_fallback(courses, profile):
    degree_level = profile.get("degree_level", "Bachelor's Degree")
    interests = [i.lower() for i in profile.get("interests", [])]
    bachelor_keywords = ['bachelor', 'b.com', 'b.sc', 'b.tech', 'b.des']
    master_keywords = ['master', 'm.com', 'm.sc', 'm.tech', 'm.des']

    filtered_by_degree = [
        course for course in courses
        if (degree_level == "Bachelor's Degree" and any(k in course.get('course', '').lower() for k in bachelor_keywords)) or \
           (degree_level == "Master's Degree" and any(k in course.get('course', '').lower() for k in master_keywords))
    ]
    if not interests: return filtered_by_degree[:10]
    matched_courses = [
        course for course in filtered_by_degree
        if any(interest in (course.get('course', '') + ' ' + ' '.join(course.get('subjects', []))).lower() for interest in interests)
    ]
    return matched_courses if matched_courses else filtered_by_degree[:10]

def extract_suggested_courses_from_chat(chat_history):
    suggested_courses = set()
    course_pattern = r'\*\*(.*?)\*\*'
    for message in chat_history:
        if message.get("role") == "assistant":
            content = message.get("content", "")
            matches = re.findall(course_pattern, content)
            for course_name in matches:
                if len(course_name.split()) > 2 and any(term in course_name for term in ["Bachelor", "Master", "B.Com", "B.Des", "M.Des", "B.Sc"]):
                    suggested_courses.add(course_name.strip())
    return list(suggested_courses)

def identify_course_from_user_query(user_message, suggested_courses):
    """
    ⭐ FINAL FIX: This robust logic cleans the course titles before matching them
    against the user's message. This correctly handles conversational filler.
    """
    if not user_message or not suggested_courses:
        return None

    user_message_lower = user_message.lower()

    # Helper function to strip university-specific suffixes and junk words
    def clean_course_name(name):
        name = name.lower()
        # Remove text after a pipe, "at JAIN", "colleges in", etc.
        name = re.sub(r'\|.*', '', name)
        name = re.sub(r'at jain.*', '', name)
        name = re.sub(r'colleges in.*', '', name)
        # Remove common prefixes/suffixes
        name = name.replace("best ", "").replace(" b.com", "bachelor of commerce").strip()
        return name

    for course in suggested_courses:
        # Clean the official course title to get its core name
        cleaned_suggested_course = clean_course_name(course)
        
        # If the core name is found within the user's message, we have a winner.
        if cleaned_suggested_course in user_message_lower:
            print(f"🎯 Found a direct match: '{cleaned_suggested_course}' in user message. Matched course: '{course}'")
            return course

    # If no direct match, return None to trigger the clarification prompt
    return None

def check_if_asking_for_more_suggestions(user_message):
    message_lower = user_message.lower()
    more_suggestions_keywords = ["more courses", "other options", "alternatives", "different", "show me more", "suggest more", "what else", "anything else", "something different"]
    return any(keyword in message_lower for keyword in more_suggestions_keywords)

# -------------------- Enhanced Context Management Functions --------------------

def is_greeting(user_input):
    """Detect if the input is a simple greeting"""
    greeting_words = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "greetings"]
    input_lower = user_input.lower().strip()
    return (any(word in input_lower for word in greeting_words) and 
            len(user_input.split()) <= 3)

def is_confusion_expression(user_input):
    """Detect expressions of confusion or uncertainty"""
    confusion_phrases = [
        "i don't know", "i dont know", "don't know", "not sure", "i'm not sure", 
        "no idea", "unsure", "i don't understand", "don't understand",
        "confused", "help me", "explain", "i have no idea",
        "no clue", "clueless", "lost", "i'm lost", "help", "hmmm", "im lost", "im not sure"
    ]
    input_lower = user_input.lower().strip()
    return any(phrase in input_lower for phrase in confusion_phrases)

def get_conversation_context(chat_history):
    """Get recent conversation context to understand the flow"""
    if len(chat_history) >= 2:
        # Look at the last few exchanges
        recent_messages = chat_history[-4:]  # Last 4 messages
        recent_text = " ".join([msg.get("content", "") for msg in recent_messages])
        return recent_text
    return None

def build_system_message(profile, response_type="normal"):
    """Build system message based on response type and user profile"""
    profile_str = json.dumps(profile, indent=2)
    
    if response_type == "confusion_with_context":
        return f"""You are a supportive academic advisor at Jain University helping a student who has expressed confusion or uncertainty. The student needs encouragement and gentle guidance.

CRITICAL RULES:
1. The student has indicated they don't know something or are confused - this is NORMAL and part of the decision-making process
2. Provide hints, clues, and encouragement to guide them toward understanding their options
3. Break down complex course information into smaller, manageable pieces
4. Use the available course data to provide specific guidance and examples
5. Be patient, supportive, and encouraging
6. Ask guiding questions to help them think through their interests and goals
7. Never make them feel bad for not knowing - confusion about career choices is natural!
8. Help them explore their interests and strengths to find the right course

Student Profile:
{profile_str}

The student is expressing uncertainty about course selection - help them explore their options step by step."""
    
    elif response_type == "greeting":
        return f"""You are a friendly, warm, and encouraging academic advisor at Jain University. You're meeting a prospective student for the first time.

CRITICAL RULES:
1. Provide a warm, welcoming greeting
2. Briefly introduce yourself as their academic advisor
3. Show enthusiasm about helping them find the right course
4. Ask an engaging question to start understanding their interests and goals
5. Keep the tone conversational and supportive
6. Don't overwhelm them with too much information initially

Student Profile:
{profile_str}

This is the beginning of your conversation with this student - make them feel welcome and excited about exploring their academic options."""
    
    else:  # normal response
        return f"""You are a friendly, patient, and encouraging academic advisor at Jain University. Your goal is to help students feel confident and informed about their course choices.

CRITICAL RULES:
1. Use the student's profile and conversation history to provide personalized advice
2. Be supportive and conversational, not robotic
3. Recommend courses based on their interests, strengths, and degree level
4. Provide clear explanations for why certain courses might be good fits
5. Always include relevant URLs when discussing specific courses
6. Ask follow-up questions to better understand their needs
7. Maintain context from previous parts of the conversation

Student Profile:
{profile_str}

Continue the conversation naturally, building on what has been discussed previously."""

def prepare_initial_prompt_with_context(profile, all_courses):
    """Enhanced initial prompt that sets up proper conversational context"""
    profile_str = json.dumps(profile, indent=2)
    relevant_courses = get_smart_course_recommendations(profile, all_courses)[:3]
    
    if not relevant_courses:
        return "I'm sorry, but I couldn't find any courses that perfectly match your unique profile in our database at the moment. It might be helpful to check the Jain University official website directly for the most current offerings."

    course_catalog_str = ""
    for c in relevant_courses:
        course_catalog_str += f"- **{c.get('course', '')}**\n  URL: {c.get('source_url', '')}\n\n"

    return f"""
    Here is the student's profile:
    {profile_str}

    Here are the top 3 courses from our database that seem like a great fit:
    {course_catalog_str}

    INSTRUCTIONS:
    1. Greet the student warmly and introduce yourself as their academic advisor
    2. Recommend ONLY the courses listed above. Use the exact course names in bold (`**Course Name**`)
    3. For each course, explain WHY it's a good match for their profile (interests, strengths)
    4. Include the course URL for each recommendation
    5. Conclude by asking: "I'd be happy to tell you more about any of these programs. Do any of them catch your eye, or would you like to explore some other possibilities?"
    """

def prepare_enhanced_context_prompt(profile, all_courses, chat_history):
    """Enhanced context-aware prompt preparation"""
    if not chat_history:
        return prepare_initial_prompt_with_context(profile, all_courses)
    
    latest_user_message = chat_history[-1].get("content", "")
    suggested_courses_from_history = extract_suggested_courses_from_chat(chat_history)
    conversation_context = get_conversation_context(chat_history)
    
    # Check different types of input
    is_greeting_input = is_greeting(latest_user_message)
    is_confusion_input = is_confusion_expression(latest_user_message)
    specific_course_requested = identify_course_from_user_query(latest_user_message, suggested_courses_from_history)
    asking_for_more = check_if_asking_for_more_suggestions(latest_user_message)

    # Handle greetings in conversation
    if is_greeting_input and len(chat_history) <= 2:
        return f"""
        The student has just greeted you. This might be their first interaction or they're re-engaging.
        
        Previous conversation context: {conversation_context or "This appears to be a new conversation"}
        
        INSTRUCTIONS:
        1. Respond warmly to their greeting
        2. If this seems like a continuation, acknowledge the previous discussion
        3. If this seems new, introduce yourself and ask about their interests
        4. Keep the response brief and welcoming
        5. Guide them toward discussing their academic goals
        """

    # Handle confusion with educational context
    if is_confusion_input:
        context_courses = get_smart_course_recommendations(profile, all_courses)[:5]
        course_options = "\n".join([f"- **{c.get('course', '')}**" for c in context_courses])
        
        return f"""
        The student is expressing confusion or uncertainty about their course selection.
        
        Conversation context: {conversation_context}
        Previously suggested courses: {', '.join(suggested_courses_from_history)}
        
        Available course options that match their profile:
        {course_options}
        
        INSTRUCTIONS:
        1. Acknowledge their uncertainty with empathy - this is normal!
        2. Help them break down their decision-making process
        3. Ask guiding questions about their interests and career goals
        4. Provide encouragement and support
        5. Offer to explore specific aspects of courses they might be interested in
        6. Use their profile information to suggest areas they might want to consider
        """

    # Handle specific course requests
    if specific_course_requested:
        course_data = next((c for c in all_courses if c.get('course', '').lower() == specific_course_requested.lower()), None)
        if not course_data:
            return f"""
            The student asked about **{specific_course_requested}** but detailed information isn't available.
            
            Conversation context: {conversation_context}
            
            INSTRUCTIONS:
            1. Acknowledge their interest in the specific course
            2. Apologize that detailed information isn't immediately available
            3. Suggest checking the official Jain University website
            4. Offer to discuss other aspects or similar courses from what's available
            5. Keep the conversation flowing by asking what specifically interests them about this course
            """

        available_info = f"""Course: **{course_data.get('course', '')}**
Description: {course_data.get('description', 'A detailed description is not available.')}
Key Subjects: {', '.join(course_data.get('subjects', ['N/A']))}
URL: {course_data.get('source_url', 'Not available.')}"""
        
        return f"""
        The student is asking about **{specific_course_requested}**.
        
        Conversation context: {conversation_context}
        
        AVAILABLE INFORMATION:
        {available_info}

        INSTRUCTIONS:
        1. Acknowledge their interest and provide the available information
        2. If information is limited, be honest about it
        3. Always provide the URL for complete details
        4. Ask follow-up questions about what specifically interests them
        5. Suggest how this course aligns with their profile and goals
        6. Keep the conversation engaging by asking about their next steps
        """

    # Handle requests for more suggestions
    if asking_for_more:
        all_relevant_courses = get_smart_course_recommendations(profile, all_courses)
        suggested_names_lower = {c.lower() for c in suggested_courses_from_history}
        new_courses = [c for c in all_relevant_courses if c.get('course', '').lower() not in suggested_names_lower][:3]

        if not new_courses:
            return f"""
            The student wants to see more options, but we've already shown the best matches.
            
            Conversation context: {conversation_context}
            Previously suggested: {', '.join(suggested_courses_from_history)}
            
            INSTRUCTIONS:
            1. Explain that the previously suggested courses are the strongest matches
            2. Offer to dive deeper into any of the already suggested courses
            3. Ask if they'd like to explore slightly different fields
            4. Suggest refining their interests or goals to find other options
            5. Keep the tone encouraging and helpful
            """

        course_catalog_str = "\n".join([f"- **{c.get('course', '')}**\n  URL: {c.get('source_url', '')}" for c in new_courses])
        return f"""
        The student wants to explore more course options.
        
        Conversation context: {conversation_context}
        Previously suggested: {', '.join(suggested_courses_from_history)}
        
        NEW COURSE OPTIONS:
        {course_catalog_str}

        INSTRUCTIONS:
        1. Enthusiastically present these new alternatives
        2. Explain why these might also be good fits based on their profile
        3. Compare or contrast with previously discussed options if relevant
        4. Ask which aspects of these new options appeal to them
        5. Keep building on the conversation naturally
        """
        
    # Handle general conversation continuation
    return f"""
    The student's message: "{latest_user_message}"
    
    Conversation context: {conversation_context}
    Previously suggested courses: {', '.join(suggested_courses_from_history)}
    
    INSTRUCTIONS:
    1. Respond naturally to their message, maintaining conversational flow
    2. Use the conversation context to provide relevant, personalized advice
    3. If their message is unclear, ask for clarification while keeping them engaged
    4. Reference previous parts of the conversation to show you're listening
    5. Guide them toward helpful next steps in their course selection process
    6. Keep the tone supportive and encouraging throughout
    """

def get_recommendation_with_enhanced_context(profile, courses, chat_history):
    """Enhanced recommendation function with full context retention"""
    
    # Debug: Print inputs to understand what we're working with
    print(f"🔍 DEBUG - Profile: {profile}")
    print(f"🔍 DEBUG - Chat history length: {len(chat_history) if chat_history else 0}")
    print(f"🔍 DEBUG - API Key present: {'Yes' if openai.api_key else 'No'}")
    print(f"🔍 DEBUG - API Base: {openai.api_base}")
    
    # Determine response type
    response_type = "normal"
    if chat_history:
        latest_message = chat_history[-1].get("content", "")
        print(f"🔍 DEBUG - Latest message: {latest_message}")
        if is_greeting(latest_message) and len(chat_history) <= 2:
            response_type = "greeting"
        elif is_confusion_expression(latest_message):
            response_type = "confusion_with_context"
    
    print(f"🔍 DEBUG - Response type: {response_type}")
    
    # Build the system message
    system_message = build_system_message(profile, response_type)
    print(f"🔍 DEBUG - System message length: {len(system_message)}")
    
    # Prepare the context-aware prompt
    context_prompt = prepare_enhanced_context_prompt(profile, courses, chat_history)
    print(f"🔍 DEBUG - Context prompt length: {len(context_prompt)}")
    
    # Build the complete message history for the AI
    messages = [{"role": "system", "content": system_message}]
    
    # Add conversation history (maintaining context)
    for msg in chat_history[:-1]:  # All messages except the latest one
        messages.append({"role": msg["role"], "content": msg["content"]})
    
    # Add the context-aware prompt for the current response
    if chat_history:
        messages.append({"role": "user", "content": context_prompt})
    else:
        # For initial conversation, use the context prompt directly
        messages = [{"role": "system", "content": system_message + "\n\n" + context_prompt}]
    
    print(f"🔍 DEBUG - Total messages to send: {len(messages)}")
    
    try:
        print("🔍 DEBUG - Attempting API call...")
        response = openai.ChatCompletion.create(
            model="mistral-tiny",
            messages=messages,
            temperature=0.6,
            max_tokens=800
        )
        print("🔍 DEBUG - API call successful!")
        return response["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"❌ ERROR: Could not get response from AI. {e}")
        print(f"❌ ERROR TYPE: {type(e).__name__}")
        print(f"❌ ERROR DETAILS: {str(e)}")
        
        # Fallback to a simpler approach
        try:
            print("🔄 Attempting fallback with simpler prompt...")
            fallback_prompt = prepare_initial_prompt(profile, courses)
            simple_response = openai.ChatCompletion.create(
                model="mistral-tiny",
                messages=[{"role": "user", "content": fallback_prompt}],
                temperature=0.6,
                max_tokens=800
            )
            print("✅ Fallback successful!")
            return simple_response["choices"][0]["message"]["content"]
        except Exception as fallback_error:
            print(f"❌ FALLBACK ALSO FAILED: {fallback_error}")
            return "I'm sorry, but I'm having a technical issue at the moment. Please try again shortly, and I'll be happy to help you explore your course options!"

# Maintain backward compatibility with the original function name
def get_recommendation_with_context(profile, courses, chat_history):
    """Wrapper function to maintain backward compatibility"""
    return get_recommendation_with_enhanced_context(profile, courses, chat_history)

# Quick test function to verify API connectivity
def test_api_connection():
    """Test basic API connectivity"""
    try:
        print("🧪 Testing API connection...")
        test_response = openai.ChatCompletion.create(
            model="mistral-tiny",
            messages=[{"role": "user", "content": "Hello, just testing the connection."}],
            temperature=0.1,
            max_tokens=50
        )
        print("✅ API connection successful!")
        return True
    except Exception as e:
        print(f"❌ API connection failed: {e}")
        return False