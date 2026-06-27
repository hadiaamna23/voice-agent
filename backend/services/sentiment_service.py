import logging
import re
from typing import Dict, List

logger = logging.getLogger("backend.services.sentiment_service")

SENTIMENT_KEYWORDS = {
    "angry": ["angry", "frustrated", "irritated", "annoyed", "upset", "furious"],
    "happy": ["happy", "pleased", "delighted", "great", "excellent", "awesome"],
    "confused": ["confused", "unclear", "not sure", "lost", "uncertain"],
    "neutral": ["okay", "fine", "average", "normal", "standard"],
}

ESCALATION_TERMS = ["complaint", "escalate", "manager", "unacceptable", "refund", "angry", "frustrated"]

TAG_PRIORITY = ["escalation", "urgent", "sensitive", "follow_up"]


class SentimentService:
    def __init__(self) -> None:
        self.tags_map = {
            "angry": ["escalation", "urgent"],
            "happy": ["positive", "customer_satisfaction"],
            "confused": ["clarification_needed", "follow_up"],
            "neutral": ["standard", "monitor"],
        }

    def analyze(self, text: str) -> Dict[str, object]:
        normalized = self._normalize(text)
        scores = self._score_sentiments(normalized)
        primary_emotion = max(scores, key=scores.get)
        confidence = round(min(1.0, scores[primary_emotion] / sum(scores.values() or [1])), 2)
        tags = self._build_tags(primary_emotion, normalized)
        escalation = self._should_escalate(normalized, primary_emotion, confidence)
        logger.debug("Sentiment analysis result: %s", {"emotion": primary_emotion, "confidence": confidence, "tags": tags})
        return {
            "emotion": primary_emotion,
            "confidence": confidence,
            "tags": tags,
            "escalation": escalation,
        }

    def _normalize(self, text: str) -> str:
        return re.sub(r"[^a-z0-9\s]", " ", text.lower())

    def _score_sentiments(self, normalized: str) -> Dict[str, float]:
        scores = {key: 0.0 for key in SENTIMENT_KEYWORDS}
        for emotion, keywords in SENTIMENT_KEYWORDS.items():
            for word in keywords:
                pattern = rf"\b{re.escape(word)}\b"
                hits = len(re.findall(pattern, normalized))
                if hits:
                    scores[emotion] += hits * (1.0 if emotion != "neutral" else 0.4)
        if all(value == 0.0 for value in scores.values()):
            scores["neutral"] = 1.0
        return scores

    def _build_tags(self, emotion: str, normalized: str) -> List[str]:
        tags = self.tags_map.get(emotion, ["general"])
        if any(term in normalized for term in ESCALATION_TERMS):
            tags = list(dict.fromkeys(tags + ["escalation", "customer_issue"]))
        if emotion == "happy":
            tags.append("promoter")
        return tags

    def _should_escalate(self, normalized: str, emotion: str, confidence: float) -> bool:
        if emotion == "angry" and confidence >= 0.6:
            return True
        if any(term in normalized for term in ESCALATION_TERMS) and confidence >= 0.4:
            return True
        return False
