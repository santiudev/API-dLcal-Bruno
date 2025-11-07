"""
Servicio para guardar datos en Google Sheets
"""
import logging
from datetime import datetime
from typing import Optional
import os
import gspread
from google.oauth2.service_account import Credentials

from config import settings
from models import RejectedPayment

logger = logging.getLogger(__name__)


class SheetsService:
    """Servicio para interactuar con Google Sheets"""
    
    def __init__(self):
        self.credentials_file = settings.google_sheets_credentials_file
        self.sheet_name = settings.google_sheets_name
        self.worksheet_name = settings.google_sheets_worksheet
        self._client = None
        self._worksheet = None
    
    def _get_worksheet(self):
        """
        Obtiene o crea la conexión al worksheet de Google Sheets
        
        Returns:
            gspread.Worksheet: Worksheet para escribir datos
        """
        if self._worksheet is not None:
            logger.info("Using cached worksheet connection")
            return self._worksheet
        
        try:
            logger.info(f"Connecting to Google Sheets...")
            logger.info(f"Looking for credentials file: {self.credentials_file}")
            
            # Define los scopes necesarios
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            
            # Crear credenciales desde el archivo JSON
            logger.info("Loading credentials from file...")
            creds = Credentials.from_service_account_file(
                self.credentials_file,
                scopes=scopes
            )
            logger.info("✅ Credentials loaded")
            
            # Autorizar el cliente
            logger.info("Authorizing gspread client...")
            self._client = gspread.authorize(creds)
            logger.info("✅ Client authorized")
            
            # Abrir el spreadsheet
            logger.info(f"Opening spreadsheet: '{self.sheet_name}'...")
            spreadsheet = self._client.open(self.sheet_name)
            logger.info(f"✅ Spreadsheet opened: {spreadsheet.title}")
            
            # Obtener o crear el worksheet
            try:
                logger.info(f"Getting worksheet: '{self.worksheet_name}'...")
                self._worksheet = spreadsheet.worksheet(self.worksheet_name)
                logger.info(f"✅ Worksheet found: {self._worksheet.title}")
            except gspread.WorksheetNotFound:
                logger.warning(f"Worksheet '{self.worksheet_name}' not found, creating it...")
                # Si no existe, crear el worksheet
                self._worksheet = spreadsheet.add_worksheet(
                    title=self.worksheet_name,
                    rows=1000,
                    cols=12
                )
                logger.info(f"✅ Worksheet created: {self._worksheet.title}")
                
                # Agregar headers (con columna de Status)
                logger.info("Adding headers...")
                self._worksheet.append_row([
                    "Payment ID",
                    "Timestamp",
                    "Status",  # Nueva columna
                    "Amount",
                    "Currency",
                    "Country",
                    "Status Detail",
                    "Status Code",
                    "Payment Method",
                    "Customer Email",
                    "Customer Phone",
                    "Order ID",
                    "Notes"
                ])
                logger.info("✅ Headers added")
            
            logger.info(f"✅ Connected to Google Sheets: {self.sheet_name}/{self.worksheet_name}")
            return self._worksheet
            
        except FileNotFoundError as e:
            logger.error(f"❌ Credentials file not found: {self.credentials_file}")
            logger.error(f"Current working directory: {os.getcwd()}")
            logger.error(f"Error: {str(e)}")
            raise Exception(f"Google Sheets credentials file not found: {self.credentials_file}")
        except Exception as e:
            logger.error(f"❌ Error connecting to Google Sheets: {str(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise
    
    def save_rejected_payment(
        self,
        payment_id: str,
        amount: float,
        currency: str,
        country: str,
        status_detail: str,
        status: str = "UNKNOWN",  # Nuevo parámetro para el estado
        status_code: Optional[str] = None,
        payment_method_type: Optional[str] = None,
        customer_email: Optional[str] = None,
        customer_phone: Optional[str] = None,
        order_id: Optional[str] = None,
        notes: Optional[str] = None
    ) -> bool:
        """
        Guarda un pago en Google Sheets (cualquier estado)
        
        Args:
            payment_id: ID del pago
            amount: Monto del pago
            currency: Moneda
            country: País
            status_detail: Razón del rechazo
            status_code: Código de estado (opcional)
            payment_method_type: Tipo de método de pago (opcional)
            customer_email: Email del cliente (opcional)
            customer_phone: Teléfono del cliente (opcional)
            order_id: ID de la orden (opcional)
            notes: Notas adicionales (opcional)
            
        Returns:
            bool: True si se guardó exitosamente
        """
        logger.info(f"📊 Attempting to save payment {payment_id} to Google Sheets...")
        logger.info(f"Credentials file: {self.credentials_file}")
        logger.info(f"Sheet name: {self.sheet_name}")
        logger.info(f"Worksheet name: {self.worksheet_name}")
        
        try:
            logger.info("Getting worksheet...")
            worksheet = self._get_worksheet()
            logger.info(f"✅ Worksheet obtained successfully")
            
            # Timestamp actual
            timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
            
            # Preparar la fila de datos (con el estado incluido)
            row = [
                payment_id,
                timestamp,
                status,  # Estado del pago
                amount,
                currency,
                country,
                status_detail or "N/A",
                status_code or "N/A",
                payment_method_type or "N/A",
                customer_email or "N/A",
                customer_phone or "N/A",
                order_id or "N/A",
                notes or ""
            ]
            
            # Agregar la fila al final del worksheet
            logger.info(f"Appending row to sheet: {row}")
            worksheet.append_row(row)
            
            logger.info(f"✅ Rejected payment saved to Google Sheets: {payment_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error saving to Google Sheets: {str(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            # No lanzar excepción para no interrumpir el flujo del webhook
            return False
    
    def save_rejected_payment_from_model(self, rejected_payment: RejectedPayment) -> bool:
        """
        Guarda un pago usando el modelo RejectedPayment (cualquier estado)
        
        Args:
            rejected_payment: Instancia del modelo RejectedPayment
            
        Returns:
            bool: True si se guardó exitosamente
        """
        return self.save_rejected_payment(
            payment_id=rejected_payment.payment_id,
            amount=rejected_payment.amount,
            currency=rejected_payment.currency,
            country=rejected_payment.country,
            status=rejected_payment.status,  # Incluir el estado
            status_detail=rejected_payment.status_detail,
            status_code=rejected_payment.status_code,
            payment_method_type=rejected_payment.payment_method_type,
            customer_email=rejected_payment.customer_email,
            customer_phone=rejected_payment.customer_phone,
            order_id=rejected_payment.order_id
        )


# Instancia singleton del servicio
sheets_service = SheetsService()

