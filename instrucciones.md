genererar codigo python, que ejecute el siguiente request cada 1 minuto :

<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:tem="http://tempuri.org">
   <soapenv:Header>
      <tem:authentication>
         <login>ltqt@lsgps.com.ar</login>
         <password>logictracker</password>
      </tem:authentication>
   </soapenv:Header>
   <soapenv:Body>
      <tem:dataRequest>
         <deviceIds>868574040321833</deviceIds>
         <deviceIds>868574040051968</deviceIds>
         <startDate>2025-10-02T13:00:00Z</startDate>
         <endDate>2025-10-02T24:00:00Z</endDate>
      </tem:dataRequest>
   </soapenv:Body>
</soapenv:Envelope>

El valor de login y password lo debe sacar de un archivo llamado .env 
Los valores de deviceIds que son varios, los debe sacar de un archivo llamado imeis.data los cuales estaran en texto plano uno debajo del otro
El endpoint es https://soap.us.navixy.com/LocationDataService
El valor de startDate debe ser la hora actual
El valor endDate deben ser 5 minutos para atras
El resultado del request, lo debe mostrar en un webserver tambien generado en el python, el xml de salida debe ser formateado para que sea legible por humanos, la pagina se debe refrescar cada 30 segundas y tiene que tener un boton que permita poner en pausa el refresco automatico.

Con el XML obtenido del request y con cada registro, se debe generar y enviar un POST:

POST /api/reception/positions/genericReception HTTP/1.1
Accept-Encoding: gzip,deflate
Content-Type: application/json
Content-Length: 149
Host: api.logictracker.com:8081
Connection: Keep-Alive
User-Agent: Apache-HttpClient/4.5.5 (Java/17.0.12)

{
"eventoId": 0,
"patente": "AE240ZE",
"fechaHora": "20251003134855",
"latitud": -34.642344,
"longitud": -58.406673,
"velocidad": 120,
"curso": 0
}

donde patente corresponde a unitPlate
fechaHora corresponde a dateGps
latitud corresponde a latitude
longitud corresponde a longitude
velocidad corresponde a speedGps

el POST y el resultado de enviarlo se debe mostrar en la web 