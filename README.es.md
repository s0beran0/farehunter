# ✈️ FareHunter — pasajes y millas en Claude

[English](README.md) · [Português](README.pt-BR.md) · **Español**

Cuenta tu viaje con tus palabras — "Ciudad de México a Madrid el 20/11, vuelta el 27/11, 2 adultos" o "Buenos Aires a Miami en diciembre" — y FareHunter busca la forma **más barata** de hacerlo. Compara:
- tarifa en efectivo;
- fechas cercanas;
- millas que ya tienes;
- compra de millas;
- transferencia de puntos de la tarjeta;
- combinaciones (ida en efectivo + vuelta con millas).

Al final entrega un ranking **en tu moneda**, con los enlaces para que compres o emitas tú mismo.

- **Funciona desde cualquier país y en cualquier moneda.** Conoce más de 30 programas de aerolíneas: LifeMiles, Copa ConnectMiles, Aeroméxico, United, American, Delta, Aeroplan, Flying Blue, Avios (Iberia/British/Qatar), Miles & More, Turkish, Emirates, LATAM Pass, Smiles, Azul…
- **También conoce puntos de tarjeta:** Amex, Chase, Citi, Capital One, Bilt, Livelo, Esfera… y con qué programas transfiere cada uno.
- **Te habla en tu idioma.** El informe sale en español, portugués o inglés; otros idiomas los traduce Claude.
- **Corre en tu computadora:** en la app Claude Desktop (pestaña **Code**) en Mac y Windows, o en Claude Code desde la terminal en Linux. Nada se aloja en un servidor.
- **Cada persona usa sus propias claves y cuentas.** **Nunca compra, no emite y nunca pide contraseñas**.

## Instalar

### Opción A — desde Claude Desktop (Mac / Windows, sin terminal)

1. Instala **Claude Desktop**: https://claude.ai/download. Inicia sesión; tu plan debe incluir Claude Code.
2. Abre la **Configuración** y, en *Personalización*, haz clic en **Plugins**.
3. Haz clic en **+ Agregar** (arriba a la derecha) → **Agregar marketplace**.
4. En el campo **URL**, escribe `s0beran0/farehunter` (o `https://github.com/s0beran0/farehunter`), elige **Usar "…"** y haz clic en **Sincronizar**.
5. En la pestaña **Descubrir** aparece **Farehunter**. Haz clic en **Agregar** a su lado.
6. Abre la pestaña **Code**, elige cualquier carpeta (ej.: `Documentos/viajes`) y escribe **`/farehunter:setup`**. Revisa tu computadora y te guía para instalar la única herramienta obligatoria (**uv**), con el enlace o el comando exacto para tu sistema.

> **¿Prefieres escribir?** Los pasos 2 a 5 se pueden reemplazar por estos dos comandos en el cuadro de mensaje de la pestaña Code:
> ```
> /plugin marketplace add s0beran0/farehunter
> /plugin install farehunter@farehunter-marketplace
> ```

### Opción B — un comando en la terminal (Mac / Windows / Linux)

Instala lo que falte y pregunta antes de cada cosa:
- **uv**, obligatorio;
- **Node.js**, opcional: solo para LATAM Pass y verificación en vivo;
- **Git**;
- **Claude Code**, solo en Linux, donde no existe Claude Desktop;
- el **plugin** en sí.

- **Mac / Linux** (Terminal):
  ```bash
  curl -fsSL https://raw.githubusercontent.com/s0beran0/farehunter/main/scripts/install.sh | bash
  ```
- **Windows** (PowerShell):
  ```powershell
  irm https://raw.githubusercontent.com/s0beran0/farehunter/main/scripts/install.ps1 | iex
  ```

Después:
- **Mac / Windows:** cierra y vuelve a abrir Claude Desktop y, en la pestaña **Code**, escribe `/farehunter:setup`.
- **Linux:** abre una terminal, ejecuta `claude` (inicia sesión la primera vez) y escribe `/farehunter:setup`.

## Usar

| Escribe | Para qué |
|---|---|
| `/farehunter:profile` | Una charla corta sobre tu país, moneda, aeropuertos, cuántas personas viajan, equipaje y en qué programas de millas y puntos tienes cuenta. Una vez; puedes cambiarlo cuando quieras. |
| `/farehunter:search Ciudad de México a Madrid 20/11, vuelta 27/11, 2 adultos` | La búsqueda. Pregunta tus **saldos de hoy** y muestra el ranking. También puedes pedirlo con tus palabras. |
| `/farehunter:miles` | Actualiza cuánto vale cada milla/punto y las promociones de compra y transferencia vigentes. Muestra el cambio y solo guarda si apruebas. |
| `/farehunter:setup` | Cuando algo falla o para revisar la instalación. |

> **¿Por qué pregunta los saldos cada vez?** Los saldos cambian con cada compra, transferencia o vencimiento. Un número guardado y olvidado llevaría a recomendaciones erróneas, así que el saldo vale solo para esa búsqueda.

## Opcionales

- **Seats.aero Pro** (US$ 9,99/mes): sin él, la disponibilidad de canjes solo aparece para vuelos que salen dentro de 60 días; con él, cualquier fecha.
  - La clave la guardas tú mismo en tu terminal, sin pasar por el chat. `/farehunter:setup` muestra el comando.
  - Verifica que la pestaña "API" aparezca en tu cuenta antes de suscribirte.
- **LATAM Pass:** el sitio solo muestra millas con sesión iniciada. Cuando haga falta, se abre una ventana del navegador y **tú** inicias sesión ahí.

## Tus datos

Se guardan en `~/.farehunter/` (en Windows, `C:\Users\<tú>\.farehunter\`):
- perfil;
- valores de las millas;
- historial de precios;
- claves (`.env`, solo en tu computadora).

Actualizar o reinstalar el plugin no borra nada. Pregunta "¿dónde están mis datos?" para ver la ruta exacta.

## Actualizar
En Claude Desktop: **Configuración → Plugins → + Agregar → Administrar marketplaces** y sincroniza **farehunter-marketplace** para descargar la versión nueva (hasta entonces la lista de plugins sigue mostrando la descripción anterior). En la pestaña Code también puedes escribir `/plugin`. Desde una terminal: `claude plugin update farehunter@farehunter-marketplace`.

## Limitaciones

- Los precios cambian hasta la emisión. Los canjes marcados como **caché** deben verificarse en el sitio del programa.
- Google Flights no tiene API oficial. Si falla, FareHunter avisa y sigue con Kiwi y las otras fuentes.
- El precio en millas puede ser menor para socios de club o categorías. El informe lo avisa.
- Smiles, LATAM y Azul tienen enlace que ya abre la búsqueda con ruta y fecha. En los demás programas, el enlace abre la página de búsqueda de canjes del programa.
- Las agencias de venta de millas quedan fuera a propósito: riesgo legal y de cancelación del boleto.
