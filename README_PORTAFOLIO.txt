CryptoAdvisor - Versión con Portafolio Manual

Cambios aplicados:
1. Se eliminó el módulo de tarjeta/cuenta de pago.
2. Se agregó módulo de Portafolio Personal:
   - Registrar cripto.
   - Registrar cantidad.
   - Registrar precio de compra.
   - Calcular valor invertido.
   - Consultar precio actual desde Binance.
   - Calcular valor actual.
   - Calcular PnL y variación porcentual.
   - Eliminar posiciones.
3. Se agregó acceso al portafolio desde el dashboard y menú lateral.
4. Se mantiene el dashboard con precios actualizados automáticamente cada 60 segundos.
5. Se mantiene el enfoque del informe: recomendaciones BUY/SELL/HOLD, sin ejecución real de órdenes.

Ejecución:
py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py

Credenciales demo:
usuario / user123
admin / admin123

Rutas principales:
http://127.0.0.1:5000/dashboard
http://127.0.0.1:5000/portafolio
http://127.0.0.1:5000/historial
http://127.0.0.1:5000/estadisticas
http://127.0.0.1:5000/admin
