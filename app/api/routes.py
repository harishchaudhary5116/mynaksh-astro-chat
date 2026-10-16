"""HTTP surface.

  POST   /chat                      the graded flow
  POST   /users                     create/update a profile
  GET    /users/{user_id}           read a profile
  GET    /users/{user_id}/brain     inspect the Shared Brain as JSON
  DELETE /users/{user_id}/memory    right to be forgotten
  GET    /health                    liveness + brain backend status
"""
