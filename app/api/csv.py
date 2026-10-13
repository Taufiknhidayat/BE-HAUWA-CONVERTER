from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from ..schemas import SubmitIn
from ..services.orders import (
    OrderValidationError,
    build_quotations_csv,
    csv_filename,
)

router = APIRouter(prefix='/api', tags=['csv'])


@router.post('/csv')
def download_csv(body: SubmitIn):
    try:
        content = build_quotations_csv(body)
        filename = csv_filename(body.platform, body.order_date, body.file_name, body.session)
    except OrderValidationError as e:
        raise HTTPException(422, str(e)) from e
    return Response(content, media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})
