import streamlit as st
from profile_builder import extract_marks_from_pdf, extract_interests_from_certificates, build_student_profile

# Quick fix: Try to import enhanced functions, fall back to basic ones
try:
    from course_matcher import load_courses, get_recommendation_with_context, test_api_connection
    API_TEST_AVAILABLE = True
except ImportError:
    try:
        from course_matcher import load_courses, get_recommendation_with_context
        API_TEST_AVAILABLE = False
    except ImportError:
        st.error("❌ Error: Could not import course_matcher functions. Please check the file.")
        st.stop()

import tempfile
import os
import time

st.set_page_config(page_title="🎓 AI Course Advisor", layout="wide")

# Initialize session state
if "page" not in st.session_state:
    st.session_state.page = "upload"

if "messages" not in st.session_state:
    st.session_state.messages = []

if "profile" not in st.session_state:
    st.session_state.profile = None

if "courses" not in st.session_state:
    st.session_state.courses = None

if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = {"marksheet": None, "certificates": []}

# Custom CSS for improved styling
st.markdown("""
<style>
/* Main styling */
.main-header {
    text-align: center;
    padding: 2rem 0;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border-radius: 10px;
    margin-bottom: 2rem;
}

.upload-container {
    background: #f8f9fa;
    padding: 2rem;
    border-radius: 15px;
    border: 2px dashed #dee2e6;
    text-align: center;
    margin: 1rem 0;
}

.question-container {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 1.5rem;
    border-radius: 10px;
    margin: 1rem 0;
    color: white;
}

.question-title {
    color: white;
    font-size: 1.1rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
}

.profile-card {
    background: transparent;
    padding: 1rem 0;
    border-bottom: 1px solid #444;
    margin: 0.5rem 0;
}

.strength-item {
    background: transparent;
    padding: 0.5rem 0;
    margin: 0.3rem 0;
    border-left: 3px solid #2196f3;
    padding-left: 0.5rem;
}

/* API Status indicators */
.api-status-good {
    background: #d4edda;
    border: 1px solid #c3e6cb;
    color: #155724;
    padding: 0.5rem;
    border-radius: 5px;
    margin: 0.5rem 0;
}

.api-status-bad {
    background: #f8d7da;
    border: 1px solid #f5c6cb;
    color: #721c24;
    padding: 0.5rem;
    border-radius: 5px;
    margin: 0.5rem 0;
}

/* Typing animation improvements */
.typing-animation {
    display: inline-block;
    overflow: hidden;
    border-right: 2px solid #ccc;
    white-space: nowrap;
    animation: typing 1s steps(40, end), blink-caret 0.75s step-end infinite;
}

@keyframes typing {
    from { width: 0 }
    to { width: 100% }
}

@keyframes blink-caret {
    from, to { border-color: transparent }
    50% { border-color: #ccc }
}

.response-container {
    background-color: transparent;
    padding: 0.5rem 0;
    border-radius: 0.5rem;
    margin: 0;
    color: inherit;
}

.stApp[data-theme="dark"] .response-container {
    background-color: transparent;
    color: #fafafa;
}

.stApp[data-theme="light"] .response-container {
    background-color: transparent;
    color: #262730;
}

/* Button styling */
.nav-button {
    background: #667eea;
    color: white;
    border: none;
    padding: 0.75rem 1.5rem;
    border-radius: 5px;
    cursor: pointer;
    font-weight: 600;
    margin: 0.5rem;
}

.nav-button:hover {
    background: #5a6fd8;
}

/* Character counter */
.char-counter {
    font-size: 0.8rem;
    color: #666;
    text-align: right;
    margin-top: 0.2rem;
}

/* Override large text in chat messages */
.stChatMessage h1, .stChatMessage h2, .stChatMessage h3 {
    font-size: 1.2rem !important;
    font-weight: bold;
    margin: 0.5rem 0;
}

.stChatMessage p {
    font-size: 1rem;
    line-height: 1.5;
}
</style>
""", unsafe_allow_html=True)

def check_api_status():
    """Check API status if available"""
    if API_TEST_AVAILABLE:
        try:
            return test_api_connection()
        except Exception as e:
            print(f"API test failed: {e}")
            return False
    return None

def display_api_status():
    """Display API status in sidebar"""
    api_status = check_api_status()
    
    if api_status is True:
        st.markdown("""
        <div class="api-status-good">
            ✅ <strong>API Status:</strong> Connected<br>
            🤖 AI recommendations available
        </div>
        """, unsafe_allow_html=True)
    elif api_status is False:
        st.markdown("""
        <div class="api-status-bad">
            ❌ <strong>API Status:</strong> Connection Failed<br>
            🔧 Check your MISTRAL_API_KEY in .env file<br>
            💡 Run <code>python api_diagnostic.py</code> for help
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("🔧 API status check not available")

def display_typing_animation(text, container):
    """Display typing animation for the response"""
    placeholder = container.empty()
    displayed_text = ""
    
    for char in text:
        displayed_text += char
        placeholder.markdown(f'<div class="response-container">{displayed_text}<span class="typing-animation">|</span></div>', unsafe_allow_html=True)
        time.sleep(0.01)
    
    # Final display without cursor
    placeholder.markdown(displayed_text)

def upload_page():
    """Document upload page"""
    st.markdown('<div class="main-header"><h1>🎓 Jain University - Design Your Degree</h1><p>Upload your academic documents to get started</p></div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("### 📄 Required Documents")
        marksheet = st.file_uploader(
            "Upload your marksheet (PDF)", 
            type=["pdf"], 
            key="marksheet_upload",
            help="Upload your latest academic marksheet or transcript"
        )
        
        st.markdown("### 🏅 Optional Documents")
        certificates = st.file_uploader(
            "Upload certificates (PDF - Optional)", 
            type=["pdf"], 
            accept_multiple_files=True,
            key="certificates_upload",
            help="Upload any certificates, awards, or additional qualifications"
        )
        
        if marksheet:
            st.session_state.uploaded_files["marksheet"] = marksheet
            st.success("✅ Marksheet uploaded successfully!")
        
        if certificates:
            st.session_state.uploaded_files["certificates"] = certificates
            st.success(f"✅ {len(certificates)} certificate(s) uploaded successfully!")
        
        st.markdown("---")
        
        col_a, col_b, col_c = st.columns([1, 1, 1])
        with col_b:
            if st.button("📝 Next: Assessment Questions", type="primary", use_container_width=True):
                if not st.session_state.uploaded_files["marksheet"]:
                    st.error("Please upload your marksheet before proceeding.")
                else:
                    st.session_state.page = "assessment"
                    st.rerun()

def assessment_page():
    """Assessment questions page with improved design"""
    st.markdown('<div class="main-header"><h1>🧠 Tell Us About Yourself</h1><p>Help us understand your interests and aspirations</p></div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 3, 1])
    
    with col2:
        # Question 1 - Degree Level Selection
        st.markdown("""
        <div class="question-container">
            <div class="question-title">1️⃣ Degree Level</div>
        </div>
        """, unsafe_allow_html=True)
        
        degree_level = st.radio(
            "What level of degree are you looking for?",
            ["Bachelor's Degree", "Master's Degree"],
            key="degree_level_input",
            help="This helps us show you the most relevant programs"
        )
        
        # Question 2 - Career Aspiration (moved from Q1)
        st.markdown("""
        <div class="question-container">
            <div class="question-title">2️⃣ Career Aspiration</div>
        </div>
        """, unsafe_allow_html=True)
        
        q1 = st.text_input(
            "Describe your aspirational career or profession in one sentence",
            max_chars=150,
            key="q1_input",
            placeholder="e.g., I want to become a data scientist who helps companies make better decisions using AI and analytics."
        )
        
        # Character counter for Q1
        char_count = len(q1) if q1 else 0
        st.markdown(f'<div class="char-counter">{char_count}/150 characters</div>', unsafe_allow_html=True)
        
        # Question 3 - Work Preferences (moved from Q2)
        st.markdown("""
        <div class="question-container">
            <div class="question-title">3️⃣ Work Environment Preferences</div>
        </div>
        """, unsafe_allow_html=True)
        
        q2 = st.multiselect(
            "What type of work environment do you enjoy?",
            ["People", "Machines or Code", "Creative Tools", "Numbers and Data", "Research & Analysis", "Problem Solving"],
            key="q2_input",
            help="Select all that apply - this helps us understand your working style"
        )
        
        # Question 4 - Subject Interests (moved from Q3)
        st.markdown("""
        <div class="question-container">
            <div class="question-title">4️⃣ Academic Interests & Learning Preferences</div>
        </div>
        """, unsafe_allow_html=True)
        
        q3 = st.text_area(
            "What subjects do you enjoy learning the most and why? Describe your learning interests in detail.",
            height=150,
            key="q3_input",
            placeholder="Describe the subjects you're passionate about, what fascinates you about them, and how you like to learn. Be as detailed as possible - this helps us understand your academic preferences better."
        )
        
        # Question 5 - Extracurricular Activities (moved from Q4)
        st.markdown("""
        <div class="question-container">
            <div class="question-title">5️⃣ Beyond Academics</div>
        </div>
        """, unsafe_allow_html=True)
        
        q4 = st.text_area(
            "Tell us about your participation in clubs, projects, competitions, or any other activities",
            height=100,
            key="q4_input",
            placeholder="Describe any projects, competitions, clubs, volunteering, internships, or other activities you've been involved in."
        )
        
        st.markdown("---")
        
        # Navigation buttons
        col_a, col_b, col_c = st.columns([1, 1, 1])
        
        with col_a:
            if st.button("⬅️ Back to Upload", use_container_width=True):
                st.session_state.page = "upload"
                st.rerun()
        
        with col_c:
            if st.button("🚀 Start Chat", type="primary", use_container_width=True):
                if not degree_level or not q1 or not q3:
                    st.error("Please select your degree level and answer at least questions 2 and 4 before proceeding.")
                else:
                    # Store responses
                    st.session_state.assessment_responses = {
                        "degree_level": degree_level, "q1": q1, "q2": q2, "q3": q3, "q4": q4
                    }
                    # Build profile
                    build_profile()
                    st.session_state.page = "chat"
                    st.rerun()

def build_profile():
    """Build student profile from uploaded documents and assessment responses"""
    try:
        # Extract marks from marksheet
        marks = {}
        if st.session_state.uploaded_files["marksheet"]:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                tmp_file.write(st.session_state.uploaded_files["marksheet"].getvalue())
                tmp_file_path = tmp_file.name
            
            marks = extract_marks_from_pdf(tmp_file_path)
            os.unlink(tmp_file_path)  # Clean up temp file
        
        # Extract interests from certificates
        interests_from_certs = []
        if st.session_state.uploaded_files["certificates"]:
            cert_paths = []
            for cert in st.session_state.uploaded_files["certificates"]:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                    tmp_file.write(cert.getvalue())
                    cert_paths.append(tmp_file.name)
            
            interests_from_certs = extract_interests_from_certificates(cert_paths)
            
            # Clean up temp files
            for path in cert_paths:
                os.unlink(path)
        
        # Get assessment responses
        responses = st.session_state.assessment_responses
        
        # Build profile
        profile = build_student_profile(
            marks=marks,
            interests_from_certs=interests_from_certs,
            degree_level=responses["degree_level"],
            q1=responses["q1"],  # Career aspiration
            q2=responses["q2"],  # Work preferences
            q3=responses["q3"],  # Academic interests
            q4=responses["q4"]   # Activities
        )
        
        st.session_state.profile = profile
        
        # Load courses
        if st.session_state.courses is None:
            st.session_state.courses = load_courses()
        
        print(f"Profile built successfully: {profile}")
        
    except Exception as e:
        st.error(f"Error building profile: {str(e)}")
        print(f"Error in build_profile: {e}")

def chat_page():
    """Chat interface for course recommendations"""
    st.markdown('<div class="main-header"><h1>🤖 Your Personal Course Advisor</h1><p>Ask me anything about courses and career paths!</p></div>', unsafe_allow_html=True)
    
    # Sidebar with profile summary and API status
    with st.sidebar:
        st.markdown("### 🔌 System Status")
        display_api_status()
        
        st.markdown("---")
        
        st.markdown("### 📊 Your Profile Summary")
        
        if st.session_state.profile:
            profile = st.session_state.profile
            
            # Academic strengths
            if profile.get('strengths'):
                st.markdown("**🎯 Academic Strengths:**")
                for strength in profile['strengths']:
                    st.markdown(f"• {strength}")
            
            # Interests
            if profile.get('interests'):
                st.markdown("**💡 Interests:**")
                for interest in profile['interests']:
                    st.markdown(f"• {interest}")
            
            # Activities and skills
            if profile.get('activities'):
                st.markdown("**🏃 Activities:**")
                for activity in profile['activities']:
                    st.markdown(f"• {activity}")
            
            # Degree level
            st.markdown(f"**🎓 Seeking:** {profile.get('degree_level', 'Not specified')}")
        
        st.markdown("---")
        if st.button("🔄 Start Over", use_container_width=True):
            # Clear session state
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
    
    # Chat interface
    st.markdown("### 💬 Chat with Your Advisor")
    
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # Initial recommendation if no messages
    if not st.session_state.messages and st.session_state.profile and st.session_state.courses:
        with st.chat_message("assistant"):
            with st.spinner("Analyzing your profile and finding the best courses..."):
                try:
                    initial_response = get_recommendation_with_context(
                        st.session_state.profile, 
                        st.session_state.courses, 
                        []
                    )
                    
                    st.markdown(initial_response)
                    
                    # Add to message history
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": initial_response
                    })
                    
                except Exception as e:
                    st.error(f"Error generating initial recommendation: {str(e)}")
                    st.info("The AI advisor is having technical difficulties. Please try again later.")
    
    # Chat input
    if prompt := st.chat_input("Ask me about courses, career prospects, or anything else..."):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Generate assistant response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    response = get_recommendation_with_context(
                        st.session_state.profile,
                        st.session_state.courses,
                        st.session_state.messages
                    )
                    
                    st.markdown(response)
                    
                    # Add to message history
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": response
                    })
                    
                except Exception as e:
                    st.error(f"Error generating response: {str(e)}")
                    st.info("The AI advisor encountered an error. Please try rephrasing your question.")

def main():
    """Main application router"""
    # Navigation based on current page
    if st.session_state.page == "upload":
        upload_page()
    elif st.session_state.page == "assessment":
        assessment_page()
    elif st.session_state.page == "chat":
        chat_page()
    else:
        # Default to upload page
        st.session_state.page = "upload"
        upload_page()

if __name__ == "__main__":
    main()