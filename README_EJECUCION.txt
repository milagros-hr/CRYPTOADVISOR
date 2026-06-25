CryptoAdvisor completo corregido

Ejecutar en Windows PowerShell:

py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py

Abrir:
http://127.0.0.1:5000

Usuarios de prueba:
usuario / user123
admin / admin123

Cambios incluidos:
- Nombre CryptoAdvisor.
- Registro de usuarios nuevos: /registro
- Cuenta/tarjeta simulada: /metodo-pago
- Dashboard con selector de criptomonedas corregido.
- Se pasa criptos y cryptos al template para evitar errores de variable.
- Compra simulada descuenta saldo; venta simulada abona saldo.
- No almacena número completo de tarjeta ni CVV.


CAMBIO APLICADO:
- Dashboard de usuario actualiza automáticamente el precio cada 60 segundos.
- El botón "Actualizar ahora" sigue disponible para forzar una consulta manual.
- Se retiró la vista de tarjeta/cuenta simulada del dashboard para mantener alineación con el informe: CryptoAdvisor emite recomendaciones, no ejecuta operaciones ni maneja pagos.
