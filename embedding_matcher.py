# embedding_matcher.py - FAISS-based semantic course matching
import json
import os
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import pickle
import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

@dataclass
class CourseMatch:
    course: Dict
    similarity: float
    rank: int

class CourseEmbeddingMatcher:
    def __init__(self, model_name='all-MiniLM-L6-v2', cache_dir='./embeddings_cache'):
        """
        FAISS-based course matcher for semantic similarity
        
        Args:
            model_name: SentenceTransformer model name
            cache_dir: Directory to cache embeddings
        """
        try:
            self.model = SentenceTransformer(model_name)
        except Exception as e:
            print(f"⚠️ Could not load SentenceTransformer: {e}")
            self.model = None
            
        self.cache_dir = cache_dir
        self.courses = []
        self.course_embeddings = None
        self.faiss_index = None
        self.course_metadata = []
        self.is_initialized = False
        
        # Create cache directory
        os.makedirs(cache_dir, exist_ok=True)
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    def initialize(self, courses_data: List[Dict], force_rebuild: bool = False) -> bool:
        """Initialize the matcher with course data"""
        if not self.model:
            self.logger.warning("SentenceTransformer not available, using fallback")
            return False
            
        self.courses = courses_data
        
        cache_file = os.path.join(self.cache_dir, 'course_embeddings.pkl')
        index_file = os.path.join(self.cache_dir, 'faiss_index.bin')
        
        try:
            if not force_rebuild and self._load_from_cache(cache_file, index_file):
                self.logger.info("✅ Loaded embeddings from cache")
                self.is_initialized = True
                return True
            
            self.logger.info("🔄 Building new embeddings...")
            self._build_embeddings()
            self._build_faiss_index()
            self._save_to_cache(cache_file, index_file)
            self.logger.info("✅ Embeddings built and cached")
            self.is_initialized = True
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize embeddings: {e}")
            return False
    
    def _build_embeddings(self) -> None:
        """Build embeddings for all courses"""
        self.course_metadata = []
        course_texts = []
        
        for i, course in enumerate(self.courses):
            # Create rich text representation
            text = self._create_course_text(course)
            course_texts.append(text)
            
            # Store metadata
            self.course_metadata.append({
                'index': i,
                'course': course,
                'text': text,
                'degree_level': self._extract_degree_level(course)
            })
        
        # Generate embeddings in batches for memory efficiency
        batch_size = 32
        all_embeddings = []
        
        for i in range(0, len(course_texts), batch_size):
            batch = course_texts[i:i + batch_size]
            batch_embeddings = self.model.encode(batch, show_progress_bar=True)
            all_embeddings.append(batch_embeddings)
        
        self.course_embeddings = np.vstack(all_embeddings)
        self.logger.info(f"Generated embeddings for {len(course_texts)} courses")
    
    def _create_course_text(self, course: Dict) -> str:
        """Create comprehensive text representation of course"""
        components = []
        
        # Core course information
        if course.get('course'):
            components.append(course['course'])
        if course.get('degree'):
            components.append(course['degree'])
        if course.get('subjects'):
            components.extend(course['subjects'])
        
        # Add semantic expansions based on course content
        course_lower = course.get('course', '').lower()
        degree_lower = course.get('degree', '').lower()
        
        semantic_terms = self._get_semantic_terms(course_lower + ' ' + degree_lower)
        components.extend(semantic_terms)
        
        return ' '.join(components)
    
    def _get_semantic_terms(self, text: str) -> List[str]:
        """Get semantic terms to enhance course representation"""
        terms = []
        
        # Technology domain
        if any(word in text for word in ['computer', 'software', 'programming', 'data', 'ai', 'tech']):
            terms.extend(['coding', 'algorithms', 'software development', 'digital technology', 'innovation'])
        
        # Design domain
        if any(word in text for word in ['design', 'animation', 'visual', 'creative', 'art', 'graphics']):
            terms.extend(['creativity', 'visual communication', 'artistic expression', 'multimedia', 'digital art'])
        
        # Business domain
        if any(word in text for word in ['commerce', 'business', 'management', 'finance', 'marketing']):
            terms.extend(['entrepreneurship', 'leadership', 'strategy', 'economics', 'corporate management'])
        
        # Sports domain
        if any(word in text for word in ['sports', 'physical', 'athletics', 'fitness', 'exercise']):
            terms.extend(['teamwork', 'discipline', 'physical fitness', 'coaching', 'competitive spirit'])
        
        # Science domain
        if any(word in text for word in ['science', 'physics', 'chemistry', 'biology', 'research']):
            terms.extend(['scientific method', 'research methodology', 'analytical thinking', 'experimentation'])
        
        return terms
    
    def _extract_degree_level(self, course: Dict) -> str:
        """Extract degree level from course"""
        course_text = (course.get('course', '') + ' ' + course.get('degree', '')).lower()
        
        if any(word in course_text for word in ['bachelor', 'b.com', 'b.sc', 'b.tech', 'b.des', 'undergraduate']):
            return 'bachelors'
        elif any(word in course_text for word in ['master', 'm.com', 'm.sc', 'm.tech', 'm.des', 'postgraduate']):
            return 'masters'
        return 'unknown'
    
    def _build_faiss_index(self) -> None:
        """Build FAISS index for fast similarity search"""
        dimension = self.course_embeddings.shape[1]
        
        # Use IndexFlatIP for exact cosine similarity
        self.faiss_index = faiss.IndexFlatIP(dimension)
        
        # Normalize embeddings for cosine similarity
        embeddings_normalized = self.course_embeddings.copy()
        faiss.normalize_L2(embeddings_normalized)
        
        # Add to index
        self.faiss_index.add(embeddings_normalized.astype('float32'))
        self.logger.info(f"Built FAISS index with {self.faiss_index.ntotal} vectors")
    
    def find_similar_courses(self, profile: Dict, degree_level: str, top_k: int = 15) -> List[CourseMatch]:
        """Find courses similar to student profile using FAISS"""
        if not self.is_initialized or not self.faiss_index:
            self.logger.warning("Matcher not initialized properly")
            return []
        
        try:
            # Create student profile embedding
            profile_text = self._create_profile_text(profile)
            profile_embedding = self.model.encode([profile_text])
            
            # Normalize for cosine similarity
            faiss.normalize_L2(profile_embedding)
            
            # Search
            similarities, indices = self.faiss_index.search(
                profile_embedding.astype('float32'), 
                min(top_k * 3, len(self.courses))  # Get more candidates for filtering
            )
            
            # Filter by degree level and create results
            matches = []
            target_degree = 'bachelors' if degree_level == "Bachelor's Degree" else 'masters'
            
            for rank, (idx, similarity) in enumerate(zip(indices[0], similarities[0])):
                metadata = self.course_metadata[idx]
                
                if metadata['degree_level'] == target_degree:
                    matches.append(CourseMatch(
                        course=metadata['course'],
                        similarity=float(similarity),
                        rank=rank
                    ))
                
                if len(matches) >= top_k:
                    break
            
            return matches
            
        except Exception as e:
            self.logger.error(f"Error in similarity search: {e}")
            return []
    
    def _create_profile_text(self, profile: Dict) -> str:
        """Create text representation of student profile for FAISS matching"""
        components = []
        
        # Academic strengths (HIGH weight - from marks)
        if profile.get('strengths'):
            strengths_text = ' '.join(profile['strengths']) + ' academic excellence'
            components.append(strengths_text)
        
        # Interests from Q3 responses (MEDIUM weight)
        if profile.get('interests'):
            interests_text = ' '.join(profile['interests']) + ' passionate about'
            components.append(interests_text)
        
        # Activities and skills from Q4 (MEDIUM weight - as requested)
        if profile.get('activities'):
            activities_text = ' '.join(profile['activities']) + ' experienced in'
            components.append(activities_text)
        if profile.get('derived_skills'):
            skills_text = ' '.join(profile['derived_skills']) + ' skilled at'
            components.append(skills_text)
        
        # Career aspiration (HIGH weight)
        if profile.get('aspiration'):
            aspiration_text = profile['aspiration'] + ' career goals'
            components.append(aspiration_text)
        
        # Work preferences from Q2
        if profile.get('work_preference'):
            work_text = ' '.join(profile['work_preference']) + ' work environment'
            components.append(work_text)
        
        return ' '.join(str(comp) for comp in components if comp)
    
    def analyze_conversation_context(self, chat_history: List[Dict]) -> Optional[Dict]:
        """Analyze conversation to understand current course context using FAISS"""
        if not self.is_initialized or not chat_history:
            return None
        
        try:
            # Extract recent conversation
            recent_messages = chat_history[-5:]
            conversation_text = ' '.join([
                msg.get('content', '') for msg in recent_messages 
                if msg.get('role') == 'user'
            ])
            
            if not conversation_text.strip():
                return None
            
            # Find most similar course to conversation
            conv_embedding = self.model.encode([conversation_text])
            faiss.normalize_L2(conv_embedding)
            
            similarities, indices = self.faiss_index.search(conv_embedding.astype('float32'), 5)
            
            # Return most similar course if similarity is high enough
            if similarities[0][0] > 0.4:  # Threshold for relevance
                best_match_idx = indices[0][0]
                return self.course_metadata[best_match_idx]['course']
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error in conversation analysis: {e}")
            return None
    
    def _save_to_cache(self, cache_file: str, index_file: str) -> None:
        """Save embeddings and index to cache"""
        try:
            cache_data = {
                'course_embeddings': self.course_embeddings,
                'course_metadata': self.course_metadata,
                'model_name': self.model.get_sentence_embedding_dimension()
            }
            
            with open(cache_file, 'wb') as f:
                pickle.dump(cache_data, f)
            
            faiss.write_index(self.faiss_index, index_file)
            self.logger.info("💾 Saved embeddings to cache")
        except Exception as e:
            self.logger.error(f"Failed to save cache: {e}")
    
    def _load_from_cache(self, cache_file: str, index_file: str) -> bool:
        """Load embeddings and index from cache"""
        try:
            if not (os.path.exists(cache_file) and os.path.exists(index_file)):
                return False
            
            with open(cache_file, 'rb') as f:
                cache_data = pickle.load(f)
            
            self.course_embeddings = cache_data['course_embeddings']
            self.course_metadata = cache_data['course_metadata']
            self.faiss_index = faiss.read_index(index_file)
            
            return True
            
        except Exception as e:
            self.logger.warning(f"Failed to load cache: {e}")
            return False

# Global matcher instance (initialized once)
_global_matcher = None

def get_enhanced_recommendations(profile: Dict, courses_data: List[Dict], chat_history: List[Dict] = None) -> Tuple[List[Dict], Optional[Dict]]:
    """Get enhanced course recommendations using FAISS"""
    global _global_matcher
    
    try:
        if _global_matcher is None:
            _global_matcher = CourseEmbeddingMatcher()
            success = _global_matcher.initialize(courses_data)
            if not success:
                print("⚠️ FAISS embeddings not available, using fallback")
                return courses_data[:10], None  # Return first 10 courses as fallback
        
        # Get course matches
        degree_level = profile.get('degree_level', "Bachelor's Degree")
        matches = _global_matcher.find_similar_courses(profile, degree_level, top_k=10)
        
        # Analyze conversation context
        context_course = None
        if chat_history:
            context_course = _global_matcher.analyze_conversation_context(chat_history)
        
        # Convert to standard format
        recommended_courses = [match.course for match in matches]
        
        print(f"🎯 FAISS found {len(recommended_courses)} relevant courses")
        if context_course:
            print(f"🔍 Detected conversation context: {context_course.get('course', 'Unknown')[:50]}...")
        
        return recommended_courses, context_course
        
    except Exception as e:
        print(f"⚠️ FAISS error, using fallback: {e}")
        # Fallback to first available courses
        return courses_data[:10], None