# ✈️ FareHunter — pasajes y millas en Claude

[English](README.md) · [Português](README.pt-BR.md) · **Español**

Cuenta tu viaje con tus palabras (en español, portugués o inglés), por ejemplo "Porto Alegre a Recife el 20/11, vuelta el 27/11, 2 adultos". FareHunter busca la forma **más barata** de hacerlo. Compara:
- tarifa en efectivo;
- fechas cercanas;
- millas que ya tienes;
- compra de millas;
- transferencia de puntos de la tarjeta;
- combinaciones (ida en efectivo + vuelta con millas).

Al final entrega un ranking en reales (BRL), con los enlaces para que compres o emitas tú mismo.

- Pensado para viajes **desde Brasil o dentro de Brasil** (Smiles, LATAM Pass, Azul Fidelidade, Livelo, Esfera; precios en BRL).
- **Corre en tu computadora**, en la app Claude Desktop (pestaña **Code**). Nada se aloja en un servidor.
- **Cada persona usa sus propias claves y cuentas.** **Nunca compra, no emite y nunca pide contraseñas**.
- Te habla en tu idioma. El informe sale en español, portugués o inglés; otros idiomas los traduce Claude.

## Instalar (una vez, ~5 minutos)

**1. Ten Claude Desktop:** https://claude.ai/download. Inicia sesión (tu plan debe incluir Claude Code).

**2. Ejecuta el instalador.** Revisa lo que falta y pregunta antes de instalar cada cosa.

- **Mac:** abre **Terminal** (Cmd+Espacio, escribe "Terminal") y pega:
  ```bash
  curl -fsSL https://raw.githubusercontent.com/s0beran0/farehunter/main/scripts/install.sh | bash
  ```
- **Windows:** abre **PowerShell** (menú Inicio, escribe "PowerShell") y pega:
  ```powershell
  irm https://raw.githubusercontent.com/s0beran0/farehunter/main/scripts/install.ps1 | iex
  ```

El instalador se encarga de:
- **uv**, obligatorio: ejecuta el motor de cálculo y descarga Python por sí solo;
- **Node.js**, opcional: solo para millas LATAM Pass y para verificar precios en vivo en Smiles;
- **Git**, solo en Windows;
- el **plugin** en sí.

**3. Si el instalador dijo que no encontró el comando `claude`**, instala el plugin desde la app. Abre Claude Desktop → pestaña **Code** → elige cualquier carpeta (ej.: `Documentos/viajes`) y escribe:
```
/plugin marketplace add s0beran0/farehunter
/plugin install farehunter@farehunter-marketplace
```

**4. Cierra y vuelve a abrir Claude Desktop.** En la pestaña Code, escribe:
```
/farehunter:setup
```
Revisa todo (internet, uv, Node, claves) y explica con calma lo que falte, con enlaces y comandos listos para pegar.

## Usar

| Escribe | Para qué |
|---|---|
| `/farehunter:profile` | Una charla corta sobre tus aeropuertos, cuántas personas viajan, equipaje, en qué programas de millas y puntos tienes cuenta y tu idioma. Una vez; puedes cambiarlo cuando quieras. |
| `/farehunter:search São Paulo a Recife 20/11, vuelta 27/11, 2 adultos` | La búsqueda. Pregunta tus **saldos de hoy** y muestra el ranking. También puedes pedirlo con tus palabras. |
| `/farehunter:miles` | Actualiza cuánto vale cada milla y las promociones de compra y transferencia vigentes. Muestra el cambio y solo guarda si apruebas. |
| `/farehunter:setup` | Cuando algo falla o para revisar la instalación. |

> **¿Por qué pregunta los saldos cada vez?** Los saldos cambian con cada compra, transferencia o vencimiento. Un número guardado y olvidado llevaría a recomendaciones erróneas, así que el saldo vale solo para esa búsqueda.

## Opcionales

- **Seats.aero Pro** (US$ 9,99/mes): sin él, las millas Smiles y Azul solo aparecen para vuelos que salen dentro de 60 días; con él, cualquier fecha.
  - La clave la guardas tú mismo en tu terminal, sin pasar por el chat. `/farehunter:setup` muestra el comando.
  - Verifica que la pestaña "API" aparezca en tu cuenta antes de suscribirte.
- **LATAM Pass:** el sitio solo muestra millas con sesión iniciada. Cuando haga falta, se abre una ventana del navegador y **tú** inicias sesión ahí. La sesión queda guardada en el navegador del plugin.

## Tus datos

Se guardan en `~/.farehunter/` (en Windows, `C:\Users\<tú>\.farehunter\`):
- perfil;
- valores de las millas;
- historial de precios;
- claves (`.env`, solo en tu computadora).

Actualizar o reinstalar el plugin no borra nada. Para ver la ruta exacta, pregunta "¿dónde están mis datos?".

## Actualizar
En Claude Desktop (pestaña Code) escribe `/plugin`, abre **farehunter** y actualiza. Desde una terminal: `claude plugin update farehunter@farehunter-marketplace`.

## Limitaciones

- Los precios cambian hasta la emisión. Las millas marcadas como **caché** deben verificarse en el sitio del programa.
- Google Flights no tiene API oficial. Si falla, FareHunter avisa y sigue con las otras fuentes.
- El precio en millas puede ser menor para socios de club o categorías (ej.: Clube Smiles, ~8%). El informe lo avisa.
- Las agencias de venta de millas (123milhas, MaxMilhas) quedan fuera a propósito: riesgo legal y de cancelación del boleto.
