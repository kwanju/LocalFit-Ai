from app.messages import (
    MSG_DISCLAIMER,
    MSG_INJURY_EMERGENCY,
    MSG_INJURY_HIGH,
    MSG_INJURY_LOW,
    MSG_INJURY_MODERATE,
)

# Keyed by DangerLevel.value (str): "low" | "moderate" | "high" | "emergency"
SAFETY_RESPONSES: dict[str, str] = {
    "low": MSG_INJURY_LOW,
    "moderate": MSG_INJURY_MODERATE,
    "high": f"{MSG_INJURY_HIGH} {MSG_DISCLAIMER}",
    "emergency": MSG_INJURY_EMERGENCY,
}
