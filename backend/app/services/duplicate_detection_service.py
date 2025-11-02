import hashlib
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from app.models.document import Document
import difflib
from datetime import datetime, timedelta

class DuplicateDetectionService:
    """Service for detecting duplicate documents"""
    
    def __init__(self):
        self.similarity_threshold = 0.8  # 80% similarity threshold for content
        self.filename_similarity_threshold = 0.7  # 70% similarity for filenames
    
    def calculate_file_hash(self, file_content: bytes) -> str:
        """Calculate SHA-256 hash of file content"""
        return hashlib.sha256(file_content).hexdigest()
    
    def check_exact_duplicate(self, db: Session, file_hash: str, owner_id: str) -> Optional[Document]:
        """Check if a file with the same hash already exists for the same user"""
        return db.query(Document).filter(
            and_(
                Document.owner_id == owner_id,
                Document.file_hash == file_hash
            )
        ).first()
    
    def check_filename_similarity(self, db: Session, filename: str, owner_id: str) -> List[Tuple[Document, float]]:
        """Check for documents with similar filenames"""
        existing_docs = db.query(Document).filter(
            Document.owner_id == owner_id
        ).all()
        
        similar_docs = []
        for doc in existing_docs:
            similarity = self._calculate_filename_similarity(filename, doc.original_filename)
            if similarity >= self.filename_similarity_threshold:
                similar_docs.append((doc, similarity))
        
        # Sort by similarity (highest first)
        return sorted(similar_docs, key=lambda x: x[1], reverse=True)
    
    def check_content_similarity(self, db: Session, extracted_text: str, owner_id: str) -> List[Tuple[Document, float]]:
        """Check for documents with similar content"""
        existing_docs = db.query(Document).filter(
            and_(
                Document.owner_id == owner_id,
                Document.extracted_text.isnot(None),
                Document.extracted_text != ""
            )
        ).all()
        
        similar_docs = []
        for doc in existing_docs:
            if doc.extracted_text:
                similarity = self._calculate_content_similarity(extracted_text, doc.extracted_text)
                if similarity >= self.similarity_threshold:
                    similar_docs.append((doc, similarity))
        
        # Sort by similarity (highest first)
        return sorted(similar_docs, key=lambda x: x[1], reverse=True)
    
    def _calculate_filename_similarity(self, filename1: str, filename2: str) -> float:
        """Calculate similarity between two filenames"""
        # Remove extensions and convert to lowercase for comparison
        name1 = filename1.lower().rsplit('.', 1)[0] if '.' in filename1 else filename1.lower()
        name2 = filename2.lower().rsplit('.', 1)[0] if '.' in filename2 else filename2.lower()
        
        # Use difflib for string similarity
        return difflib.SequenceMatcher(None, name1, name2).ratio()
    
    def _calculate_content_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two text contents"""
        # Normalize text (remove extra whitespace, convert to lowercase)
        text1_normalized = ' '.join(text1.lower().split())
        text2_normalized = ' '.join(text2.lower().split())
        
        # Use difflib for text similarity
        return difflib.SequenceMatcher(None, text1_normalized, text2_normalized).ratio()
    
    def detect_all_duplicates(self, db: Session, file_content: bytes, filename: str, 
                            extracted_text: str, owner_id: str) -> Dict[str, Any]:
        """Comprehensive duplicate detection"""
        results = {
            'exact_duplicate': None,
            'filename_similarities': [],
            'content_similarities': [],
            'recommendation': 'safe_to_upload'
        }
        
        # Check for exact duplicates (by hash)
        file_hash = self.calculate_file_hash(file_content)
        exact_duplicate = self.check_exact_duplicate(db, file_hash, owner_id)
        if exact_duplicate:
            results['exact_duplicate'] = exact_duplicate
            results['recommendation'] = 'exact_duplicate_found'
            return results
        
        # Check for filename similarities
        filename_similarities = self.check_filename_similarity(db, filename, owner_id)
        results['filename_similarities'] = filename_similarities
        
        # Check for content similarities
        content_similarities = self.check_content_similarity(db, extracted_text, owner_id)
        results['content_similarities'] = content_similarities
        
        # Determine recommendation
        if filename_similarities and filename_similarities[0][1] > 0.9:
            results['recommendation'] = 'high_filename_similarity'
        elif content_similarities and content_similarities[0][1] > 0.9:
            results['recommendation'] = 'high_content_similarity'
        elif (filename_similarities and filename_similarities[0][1] > 0.7) or \
             (content_similarities and content_similarities[0][1] > 0.7):
            results['recommendation'] = 'moderate_similarity'
        
        return results
    
    def get_duplicate_summary(self, duplicate_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a user-friendly summary of duplicate detection results"""
        summary = {
            'has_duplicates': False,
            'warning_level': 'none',  # none, low, medium, high
            'message': '',
            'similar_documents': []
        }
        
        if duplicate_results['exact_duplicate']:
            summary['has_duplicates'] = True
            summary['warning_level'] = 'high'
            summary['message'] = 'This file appears to be an exact duplicate of an existing document.'
            summary['similar_documents'].append({
                'id': duplicate_results['exact_duplicate'].id,
                'title': duplicate_results['exact_duplicate'].title or duplicate_results['exact_duplicate'].original_filename,
                'similarity': 1.0,
                'type': 'exact_duplicate',
                'uploaded_at': duplicate_results['exact_duplicate'].created_at
            })
        else:
            # Check filename similarities
            for doc, similarity in duplicate_results['filename_similarities'][:3]:  # Top 3
                if similarity > 0.8:
                    summary['similar_documents'].append({
                        'id': doc.id,
                        'title': doc.title or doc.original_filename,
                        'similarity': similarity,
                        'type': 'filename_similarity',
                        'uploaded_at': doc.created_at
                    })
            
            # Check content similarities
            for doc, similarity in duplicate_results['content_similarities'][:3]:  # Top 3
                if similarity > 0.8:
                    summary['similar_documents'].append({
                        'id': doc.id,
                        'title': doc.title or doc.original_filename,
                        'similarity': similarity,
                        'type': 'content_similarity',
                        'uploaded_at': doc.created_at
                    })
            
            if summary['similar_documents']:
                summary['has_duplicates'] = True
                if any(doc['similarity'] > 0.9 for doc in summary['similar_documents']):
                    summary['warning_level'] = 'high'
                    summary['message'] = 'This document appears very similar to existing documents. Please review before uploading.'
                elif any(doc['similarity'] > 0.7 for doc in summary['similar_documents']):
                    summary['warning_level'] = 'medium'
                    summary['message'] = 'This document may be similar to existing documents. Please review before uploading.'
                else:
                    summary['warning_level'] = 'low'
                    summary['message'] = 'Some similarity detected with existing documents. Please review before uploading.'
        
        return summary
