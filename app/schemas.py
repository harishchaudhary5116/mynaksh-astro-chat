"""Pydantic request/response models.

Validation here is what gives us the brief's "invalid input" handling for free:
a bad body never reaches the service layer, it returns 422.

ChatResponse extends the brief's shape with `retrieval_strategy` and `degraded`
(the brief allows extending the format where useful).
"""
