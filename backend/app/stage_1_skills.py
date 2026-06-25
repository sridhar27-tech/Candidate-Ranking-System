import functools
import cpp_ranker  # Imports your compiled C++ binary module natively!
from app.schemas import SkillModel
# pyrefly: ignore [missing-import]
from sentence_transformers import SentenceTransformer
from typing import List

# Keep the transformer instantiation clear of the loop execution context
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

@functools.lru_cache(maxsize=50000)
def get_embedding_list(text: str) -> List[float]:
    return embedding_model.encode(text).tolist()

def evaluate_semantic_skills(job_description_text: str, candidate_skills: List[SkillModel]) -> float:
    if not candidate_skills:
        return 0.0

    # 1. Compute vectors into standard array representations
    jd_vector = get_embedding_list(job_description_text)
    
    # 2. Package skills into a clean list of tuples expected by the C++ memory module
    prepared_skills = []
    for skill in candidate_skills:  
        skill_vector = get_embedding_list(skill.name)
        prepared_skills.append((skill_vector, skill.proficiency.lower(), skill.duration_months))
    
    # 3. Ship data over the bridge—C++ processes it at bare-metal execution speeds
    final_score = cpp_ranker.calculate_fast_stage_1(jd_vector, prepared_skills)
    
    # ABSOLUTE SAFETY GUARDRAIL: Clamp the C++ return value between 0.0 and 100.0
    return float(min(max(final_score, 0.0), 100.0))