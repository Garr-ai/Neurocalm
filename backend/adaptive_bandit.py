import random
from typing import Dict, List


class AdaptiveBandit:
    def __init__(self,
                 techniques: List[str],
                 epsilon: float = 0.2,
                 alpha: float = 0.3):
        self.techniques = techniques
        self.epsilon = epsilon
        self.alpha = alpha
        self.Q: Dict[str, float] = {t: 0.0 for t in techniques}
        self.N: Dict[str, int] = {t: 0 for t in techniques}

    def calibrate(self, initial_scores: Dict[str, float]):
        for t, val in initial_scores.items():
            if t in self.Q:
                self.Q[t] = float(val)
                self.N[t] = 1

    def select(self) -> str:
        if random.random() < self.epsilon:
            return random.choice(self.techniques)
        return max(self.techniques, key=lambda t: self.Q[t])

    def update(self, technique: str, reward: float):
        if technique not in self.Q:
            return
        old_q = self.Q[technique]
        new_q = (1.0 - self.alpha) * old_q + self.alpha * reward
        self.Q[technique] = new_q
        self.N[technique] += 1

    def get_rankings(self):
        return sorted(self.Q.items(), key=lambda x: x[1], reverse=True)

    def __str__(self):
        return str(self.get_rankings())

