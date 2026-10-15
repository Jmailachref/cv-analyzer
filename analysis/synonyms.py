"""Default synonyms, so a criterion named "JavaScript" also finds "JS" and "Node.js".

Keys and values are written as a CV would spell them; matching normalises
case and accents. A grid can turn these off per criterion and list its own.
"""
from __future__ import annotations

from analysis.text import normalize

SYNONYMS: dict[str, list[str]] = {
    "python": ["python", "python3", "django", "flask", "fastapi", "pandas", "numpy"],
    "javascript": ["javascript", "js", "ecmascript", "es6", "node.js", "nodejs", "node"],
    "typescript": ["typescript"],
    "java": ["java", "jvm", "spring", "spring boot", "j2ee", "jakarta ee"],
    "kotlin": ["kotlin"],
    "c": ["langage c", "ansi c"],
    "cpp": ["c++", "cpp", "c plus plus"],
    "c#": ["c#", "csharp", ".net", "dotnet", "asp.net"],
    "go": ["golang", "go lang", "go"],
    "rust": ["rust"],
    "php": ["php", "symfony", "laravel"],
    "ruby": ["ruby", "rails", "ruby on rails"],
    "sql": ["sql", "postgresql", "postgres", "mysql", "mariadb", "oracle", "sql server", "t-sql", "pl/sql", "sqlite"],
    "nosql": ["nosql", "mongodb", "mongo", "cassandra", "dynamodb", "redis"],
    "react": ["react", "react.js", "reactjs", "next.js", "nextjs"],
    "angular": ["angular", "angularjs"],
    "vue": ["vue", "vue.js", "vuejs", "nuxt"],
    "html": ["html", "html5"],
    "css": ["css", "css3", "sass", "scss", "tailwind"],
    "docker": ["docker", "dockerfile", "docker compose"],
    "kubernetes": ["kubernetes", "k8s", "openshift", "helm"],
    "aws": ["aws", "amazon web services", "ec2", "s3", "lambda"],
    "azure": ["azure", "microsoft azure"],
    "gcp": ["gcp", "google cloud", "bigquery"],
    "git": ["git", "github", "gitlab", "bitbucket"],
    "linux": ["linux", "unix", "bash", "shell", "ubuntu", "debian"],
    "ci/cd": ["ci/cd", "jenkins", "github actions", "gitlab ci", "integration continue"],
    "terraform": ["terraform", "infrastructure as code", "iac"],
    "data": [
        "data", "data science", "science des donnees", "data scientist", "data analyst", "data engineer",
        "machine learning", "ml", "big data", "analyse de donnees", "data analysis",
    ],
    "machine learning": [
        "machine learning", "ml", "apprentissage automatique", "deep learning", "scikit-learn", "sklearn",
        "tensorflow", "pytorch", "keras",
    ],
    "spark": ["spark", "pyspark", "apache spark", "databricks"],
    "excel": ["excel", "vba", "tableur"],
    "power bi": ["power bi", "powerbi"],
    "tableau": ["tableau software", "tableau desktop"],
    "agile": ["agile", "scrum", "kanban", "sprint"],
    "rest": ["restful", "api rest", "rest api"],
    "graphql": ["graphql"],
    "testing": ["tests unitaires", "unit tests", "pytest", "junit", "jest", "tdd", "selenium", "cypress"],
    "english": ["anglais", "english", "toeic", "toefl", "ielts"],
    "french": ["francais", "french", "delf", "dalf"],
}

_BY_NAME = {normalize(k): v for k, v in SYNONYMS.items()}


def synonyms_for(name: str) -> list[str]:
    """The default synonyms for a criterion name, or just the name when none are known."""
    return _BY_NAME.get(normalize(name).strip(), [name])
