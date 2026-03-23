from fastapi import APIRouter
from fastapi.responses import JSONResponse

from models.ui_models import UIBlueprintError, UIGenerateCodeRequest, UIGenerateCodeResponse
from services.ui_code_service import generate_ui_code_from_blueprint
from services.ui_service import UIServiceError


router = APIRouter(prefix="/ui", tags=["ui"])


@router.post(
    "/generate-code",
    response_model=UIGenerateCodeResponse,
    responses={502: {"model": UIBlueprintError}},
)
async def generate_ui_code(request: UIGenerateCodeRequest):
    try:
        code_bundle = await generate_ui_code_from_blueprint(
            blueprint=request.blueprint.model_dump(),
            project_name=request.projectName,
        )
        return code_bundle
    except UIServiceError as e:
        return JSONResponse(
            status_code=502,
            content=UIBlueprintError(error="UI code generation failed", details=str(e)).model_dump(),
        )
    except RuntimeError as e:
        return JSONResponse(
            status_code=502,
            content=UIBlueprintError(error="AI service error", details=str(e)).model_dump(),
        )
    except Exception:
        return JSONResponse(
            status_code=500,
            content=UIBlueprintError(error="Internal Server Error").model_dump(),
        )
