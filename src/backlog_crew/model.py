from strands.models import BedrockModel

from backlog_crew.config import settings


def make_model(agent_name: str) -> BedrockModel:
    s = settings()
    return BedrockModel(model_id=s.model_id_for(agent_name), region_name=s.aws_region)
