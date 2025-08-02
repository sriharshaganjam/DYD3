# enhanced_embedding_matcher.py - FAISS-based semantic course matching with scraped data integration
import json
import os
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import pickle
import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import hashlib

@dataclass
class CourseMatch:
    course: Dict
    similarity: float
    rank: int
    enhanced_data: Optional[Dict] = None

class EnhancedCourseEmbeddingMatcher:
    def __init__(self, model_name='all-MiniLM-L6-v2', cache_dir='./embeddings_cache'):
        """
        Enhanced FAISS-based course matcher with scraped data integration
        
        Args:
            model_name: SentenceTransformer model name
            cache_dir: Directory to cache embeddings and enhanced data
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
        self.enhanced_course_data = {}  # Store scraped data
        self.is_initialized = False
        
        # Create cache directory
        os.makedirs(cache_dir, exist_ok=True)
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    def initialize(self, courses_data: List[Dict], force_rebuild: bool = False) -> bool:
        """Initialize the matcher with course data and load any cached scraped data"""
        if not self.model:
            self.logger.warning("SentenceTransformer not available, using fallback")
            return False
            
        self.courses = courses_data
        
        # Load enhanced course data from previous sessions
        self._load_enhanced_course_data()
        
        cache_file = os.path.join(self.cache_dir, 'course_embeddings_enhanced.pkl')
        index_file = os.path.join(self.cache_dir, 'faiss_index_enhanced.bin')
        
        try:
            if not force_rebuild and self._load_from_cache(cache_file, index_file):
                self.logger.info("✅ Loaded enhanced embeddings from cache")
                self.is_initialized = True
                return True
            
            self.logger.info("🔄 Building new enhanced embeddings...")
            self._build_enhanced_embeddings()
            self._build_faiss_index()
            self._save_to_cache(cache_file, index_file)
            self.logger.info("✅ Enhanced embeddings built and cached")
            self.is_initialized = True
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize enhanced embeddings: {e}")
            return False
    
    def add_scraped_course_data(self, course_url: str, scraped_data: Dict) -> bool:
        """
        Add scraped course data and re-embed the course with enhanced information
        
        Args:
            course_url: URL of the course that was scraped
            scraped_data: Detailed scraped course information
            
        Returns:
            bool: Success status
        """
        try:
            # Find the course in our database
            target_course_idx = None
            for idx, course in enumerate(self.courses):
                if course.get('source_url') == course_url:
                    target_course_idx = idx
                    break
            
            if target_course_idx is None:
                self.logger.warning(f"Course with URL {course_url} not found in database")
                return False
            
            # Store enhanced data
            course_id = self._get_course_id(self.courses[target_course_idx])
            self.enhanced_course_data[course_id] = {
                'scraped_data': scraped_data,
                'scraped_at': datetime.now().isoformat(),
                'course_url': course_url
            }
            
            # Save enhanced data
            self._save_enhanced_course_data()
            
            # Re-embed this course with enhanced data
            enhanced_text = self._create_enhanced_course_text(self.courses[target_course_idx], scraped_data)
            enhanced_embedding = self.model.encode([enhanced_text])[0]
            
            # Update the embedding in our index
            if self.course_embeddings is not None and self.faiss_index is not None:
                # Replace the embedding for this course
                self.course_embeddings[target_course_idx] = enhanced_embedding
                
                # Rebuild FAISS index (for simplicity - could be optimized)
                self._rebuild_faiss_index()
                
                # Update metadata
                if target_course_idx < len(self.course_metadata):
                    self.course_metadata[target_course_idx]['enhanced_data'] = scraped_data
                    self.course_metadata[target_course_idx]['text'] = enhanced_text
            
            self.logger.info(f"✅ Enhanced course data added for: {self.courses[target_course_idx].get('course', '')}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add scraped data: {e}")
            return False
    
    def _get_course_id(self, course: Dict) -> str:
        """Generate a unique ID for a course"""
        course_name = course.get('course', '')
        course_url = course.get('source_url', '')
        return hashlib.md5(f"{course_name}_{course_url}".encode()).hexdigest()
    
    def _create_enhanced_course_text(self, course: Dict, scraped_data: Optional[Dict] = None) -> str:
        """Create comprehensive text representation including scraped data"""
        components = []
        
        # Basic course information
        if course.get('course'):
            components.append(course['course'])
        if course.get('degree'):
            components.append(course['degree'])
        if course.get('subjects'):
            components.extend(course['subjects'])
        if course.get('description'):
            components.append(course['description'])
        
        # Add scraped data if available
        course_id = self._get_course_id(course)
        if scraped_data is None and course_id in self.enhanced_course_data:
            scraped_data = self.enhanced_course_data[course_id]['scraped_data']
        
        if scraped_data:
            # Add detailed scraped information
            if scraped_data.get('subjects'):
                components.extend(scraped_data['subjects'])
            
            if scraped_data.get('curriculum'):
                # Add curriculum items (limit to avoid too much noise)
                curriculum_text = ' '.join(scraped_data['curriculum'][:10])
                components.append(curriculum_text)
            
            if scraped_data.get('description'):
                components.append(scraped_data['description'][:500])  # Limit length
            
            if scraped_data.get('career_prospects'):
                career_text = ' '.join(scraped_data['career_prospects'][:3])
                components.append(career_text)
            
            if scraped_data.get('highlights'):
                highlights_text = ' '.join(scraped_data['highlights'][:5])
                components.append(highlights_text)
        
        # Add semantic expansions
        text_for_expansion = ' '.join(str(comp) for comp in components).lower()
        semantic_terms = self._get_semantic_terms(text_for_expansion)
        components.extend(semantic_terms)
        
        return ' '.join(str(comp) for comp in components if comp)
    
    def _build_enhanced_embeddings(self) -> None:
        """Build embeddings for all courses with enhanced data"""
        self.course_metadata = []
        course_texts = []
        
        for i, course in enumerate(self.courses):
            # Check if we have enhanced data for this course
            course_id = self._get_course_id(course)
            scraped_data = None
            if course_id in self.enhanced_course_data:
                scraped_data = self.enhanced_course_data[course_id]['scraped_data']
            
            # Create enhanced text representation
            text = self._create_enhanced_course_text(course, scraped_data)
            course_texts.append(text)
            
            # Store metadata
            self.course_metadata.append({
                'index': i,
                'course': course,
                'text': text,
                'degree_level': self._extract_degree_level(course),
                'enhanced_data': scraped_data,
                'has_enhanced_data': scraped_data is not None
            })
        
        # Generate embeddings in batches
        batch_size = 32
        all_embeddings = []
        
        for i in range(0, len(course_texts), batch_size):
            batch = course_texts[i:i + batch_size]
            batch_embeddings = self.model.encode(batch, show_progress_bar=True)
            all_embeddings.append(batch_embeddings)
        
        self.course_embeddings = np.vstack(all_embeddings)
        
        enhanced_count = sum(1 for meta in self.course_metadata if meta['has_enhanced_data'])
        self.logger.info(f"Generated embeddings for {len(course_texts)} courses ({enhanced_count} with enhanced data)")
    
    def _rebuild_faiss_index(self) -> None:
        """Rebuild FAISS index with current embeddings"""
        if self.course_embeddings is None:
            return
            
        dimension = self.course_embeddings.shape[1]
        self.faiss_index = faiss.IndexFlatIP(dimension)
        
        # Normalize embeddings for cosine similarity
        embeddings_normalized = self.course_embeddings.copy()
        faiss.normalize_L2(embeddings_normalized)
        
        # Add to index
        self.faiss_index.add(embeddings_normalized.astype('float32'))
    
    def _build_faiss_index(self) -> None:
        """Build FAISS index for fast similarity search"""
        self._rebuild_faiss_index()
        self.logger.info(f"Built FAISS index with {self.faiss_index.ntotal} vectors")
    
    def find_similar_courses(self, profile: Dict, degree_level: str, top_k: int = 15) -> List[CourseMatch]:
        """Find courses similar to student profile using enhanced FAISS matching"""
        if not self.is_initialized or not self.faiss_index:
            self.logger.warning("Enhanced matcher not initialized properly")
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
                min(top_k * 3, len(self.courses))
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
                        rank=rank,
                        enhanced_data=metadata.get('enhanced_data')
                    ))
                
                if len(matches) >= top_k:
                    break
            
            # Log enhanced data usage
            enhanced_matches = sum(1 for m in matches if m.enhanced_data is not None)
            self.logger.info(f"Found {len(matches)} matches ({enhanced_matches} with enhanced data)")
            
            return matches
            
        except Exception as e:
            self.logger.error(f"Error in enhanced similarity search: {e}")
            return []
    
    def semantic_search_scraped_content(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        Perform semantic search specifically on scraped content
        
        Args:
            query: Search query
            top_k: Number of results to return
            
        Returns:
            List of courses with relevant scraped content
        """
        if not self.is_initialized:
            return []
        
        try:
            query_embedding = self.model.encode([query])
            faiss.normalize_L2(query_embedding)
            
            similarities, indices = self.faiss_index.search(query_embedding.astype('float32'), top_k * 2)
            
            results = []
            for idx, similarity in zip(indices[0], similarities[0]):
                metadata = self.course_metadata[idx]
                if metadata.get('enhanced_data'):  # Only return courses with scraped data
                    results.append({
                        'course': metadata['course'],
                        'enhanced_data': metadata['enhanced_data'],
                        'similarity': float(similarity),
                        'course_name': metadata['course'].get('course', '')
                    })
                
                if len(results) >= top_k:
                    break
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error in semantic search of scraped content: {e}")
            return []
    
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
        
        return terms
    
    def _extract_degree_level(self, course: Dict) -> str:
        """Extract degree level from course"""
        course_text = (course.get('course', '') + ' ' + course.get('degree', '')).lower()
        
        if any(word in course_text for word in ['bachelor', 'b.com', 'b.sc', 'b.tech', 'b.des', 'undergraduate']):
            return 'bachelors'
        elif any(word in course_text for word in ['master', 'm.com', 'm.sc', 'm.tech', 'm.des', 'postgraduate']):
            return 'masters'
        return 'unknown'
    
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
        
        # Activities and skills from Q4 (MEDIUM weight)
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
    
    def _save_enhanced_course_data(self) -> None:
        """Save enhanced course data to persistent storage"""
        try:
            enhanced_data_file = os.path.join(self.cache_dir, 'enhanced_course_data.json')
            with open(enhanced_data_file, 'w') as f:
                json.dump(self.enhanced_course_data, f, indent=2)
            self.logger.info("💾 Saved enhanced course data")
        except Exception as e:
            self.logger.error(f"Failed to save enhanced course data: {e}")
    
    def _load_enhanced_course_data(self) -> None:
        """Load enhanced course data from persistent storage"""
        try:
            enhanced_data_file = os.path.join(self.cache_dir, 'enhanced_course_data.json')
            if os.path.exists(enhanced_data_file):
                with open(enhanced_data_file, 'r') as f:
                    self.enhanced_course_data = json.load(f)
                self.logger.info(f"📁 Loaded {len(self.enhanced_course_data)} enhanced course records")
            else:
                self.enhanced_course_data = {}
        except Exception as e:
            self.logger.warning(f"Failed to load enhanced course data: {e}")
            self.enhanced_course_data = {}
    
    def _save_to_cache(self, cache_file: str, index_file: str) -> None:
        """Save embeddings and index to cache"""
        try:
            cache_data = {
                'course_embeddings': self.course_embeddings,
                'course_metadata': self.course_metadata,
                'model_name': self.model.get_sentence_embedding_dimension(),
                'enhanced_data_count': len(self.enhanced_course_data)
            }
            
            with open(cache_file, 'wb') as f:
                pickle.dump(cache_data, f)
            
            faiss.write_index(self.faiss_index, index_file)
            self.logger.info("💾 Saved enhanced embeddings to cache")
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

# Global enhanced matcher instance
_global_enhanced_matcher = None

def get_enhanced_recommendations(profile: Dict, courses_data: List[Dict], chat_history: List[Dict] = None) -> Tuple[List[Dict], Optional[Dict]]:
    """Get enhanced course recommendations using FAISS with scraped data integration"""
    global _global_enhanced_matcher
    
    try:
        if _global_enhanced_matcher is None:
            _global_enhanced_matcher = EnhancedCourseEmbeddingMatcher()
            success = _global_enhanced_matcher.initialize(courses_data)
            if not success:
                print("⚠️ Enhanced FAISS embeddings not available, using fallback")
                return courses_data[:10], None
        
        # Get course matches with enhanced data
        degree_level = profile.get('degree_level', "Bachelor's Degree")
        matches = _global_enhanced_matcher.find_similar_courses(profile, degree_level, top_k=10)
        
        # Analyze conversation context
        context_course = None
        if chat_history:
            context_course = _global_enhanced_matcher.analyze_conversation_context(chat_history)
        
        # Convert to standard format, preserving enhanced data
        recommended_courses = []
        for match in matches:
            course_data = match.course.copy()
            if match.enhanced_data:
                course_data['_enhanced_data'] = match.enhanced_data  # Store enhanced data
            recommended_courses.append(course_data)
        
        enhanced_count = sum(1 for match in matches if match.enhanced_data)
        print(f"🎯 Enhanced FAISS found {len(recommended_courses)} relevant courses ({enhanced_count} with scraped data)")
        
        return recommended_courses, context_course
        
    except Exception as e:
        print(f"⚠️ Enhanced FAISS error, using fallback: {e}")
        return courses_data[:10], None

def add_scraped_data_to_embeddings(course_url: str, scraped_data: Dict) -> bool:
    """
    Add scraped course data to the FAISS embeddings
    
    Args:
        course_url: URL of the scraped course
        scraped_data: Detailed scraped information
        
    Returns:
        bool: Success status
    """
    global _global_enhanced_matcher
    
    if _global_enhanced_matcher is None:
        print("⚠️ Enhanced matcher not initialized")
        return False
    
    return _global_enhanced_matcher.add_scraped_course_data(course_url, scraped_data)

def semantic_search_scraped_content(query: str, top_k: int = 5) -> List[Dict]:
    """
    Perform semantic search on scraped course content
    
    Args:
        query: Search query
        top_k: Number of results
        
    Returns:
        List of relevant courses with scraped data
    """
    global _global_enhanced_matcher
    
    if _global_enhanced_matcher is None:
        print("⚠️ Enhanced matcher not initialized")
        return []
    
    return _global_enhanced_matcher.semantic_search_scraped_content(query, top_k)