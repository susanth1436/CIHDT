/* Enrolling a USB peripheral the visitor picks, through WebUSB.
 *
 * This is the only script the console serves, and it loads on one page. Every
 * other page remains pure HTML over Post/Redirect/Get, because every other
 * action is a decision the operator takes on the server. This one cannot be:
 * the bus is attached to the visitor's machine, and only the browser can
 * reach it -- and only after the visitor has picked a device in the chooser
 * the browser itself draws, which no page can script around.
 *
 * What is read here are descriptors, available without claiming the device.
 * Claiming is deliberately not attempted: a webcam is held by the operating
 * system's UVC driver and a claim would fail, so the code does not pretend
 * otherwise. Identity, class, revision and declared bus power come off the
 * descriptors; host telemetry comes from the server, and the page says so.
 */
(function () {
  "use strict";

  var btn = document.getElementById("webusb-pick");
  var out = document.getElementById("webusb-status");
  var form = document.getElementById("webusb-form");
  var field = document.getElementById("webusb-payload");
  if (!btn || !out || !form || !field) { return; }

  function say(text, kind) {
    out.textContent = text;
    out.className = "note " + (kind || "");
  }

  if (!("usb" in navigator)) {
    btn.disabled = true;
    say("This browser has no WebUSB support. Chrome or Edge can share a " +
        "device; Firefox and Safari cannot. The simulated fleet works in " +
        "every browser.", "warn");
    return;
  }
  if (!window.isSecureContext) {
    btn.disabled = true;
    say("WebUSB needs a secure context. Open this console over HTTPS, or " +
        "on localhost.", "warn");
    return;
  }

  /* Interface classes across every configuration, most specific first.
   * A composite device declares 0x00 or 0xEF at the device level and puts
   * the real class here, so this is what identifies a webcam as video. */
  function interfaceClasses(device) {
    var seen = [];
    (device.configurations || []).forEach(function (cfg) {
      (cfg.interfaces || []).forEach(function (iface) {
        (iface.alternates || []).forEach(function (alt) {
          if (seen.indexOf(alt.interfaceClass) === -1) {
            seen.push(alt.interfaceClass);
          }
        });
      });
    });
    return seen;
  }

  /* MaxPower off the active configuration, in milliamps. The browser does
   * not expose it directly, so it is read from the configuration descriptor
   * when present and left out otherwise -- never guessed. */
  function maxPowerMa(device) {
    var cfg = device.configuration ||
              (device.configurations && device.configurations[0]);
    if (!cfg) { return null; }
    var v = cfg.maxPower;                     /* milliamps, where exposed */
    return (typeof v === "number" && isFinite(v)) ? v : null;
  }

  function describe(device) {
    return {
      vendorId: device.vendorId,
      productId: device.productId,
      deviceClass: device.deviceClass,
      deviceSubclass: device.deviceSubclass,
      deviceProtocol: device.deviceProtocol,
      interfaceClasses: interfaceClasses(device),
      manufacturerName: device.manufacturerName || "",
      productName: device.productName || "",
      serialNumber: device.serialNumber || "",
      usbVersionMajor: device.usbVersionMajor,
      usbVersionMinor: device.usbVersionMinor,
      deviceVersionMajor: device.deviceVersionMajor,
      deviceVersionMinor: device.deviceVersionMinor,
      configurationCount: (device.configurations || []).length,
      configurationMaxPowerMa: maxPowerMa(device)
    };
  }

  btn.addEventListener("click", function () {
    say("Waiting for you to choose a device…");
    /* An empty filter list shows everything attached. The browser draws the
     * chooser and the page never learns about devices the visitor declines. */
    navigator.usb.requestDevice({ filters: [] }).then(function (device) {
      var payload = describe(device);
      var label = payload.productName || payload.manufacturerName ||
                  ("USB device " + payload.vendorId + ":" + payload.productId);

      /* Opening is optional and often refused -- the OS driver already holds
       * a webcam. The descriptors are already in hand either way, so a
       * failure here is reported, not treated as fatal. */
      device.open().then(function () {
        say("Read " + label + " and opened it. Enrolling…", "ok");
        return device.close();
      }).catch(function () {
        say("Read " + label + " from its descriptors. The operating system " +
            "holds the device, so it could not also be opened here — " +
            "identity and declared power are still genuine. Enrolling…",
            "ok");
      }).then(function () {
        field.value = JSON.stringify(payload);
        form.submit();
      });
    }).catch(function (err) {
      if (err && err.name === "NotFoundError") {
        say("No device chosen.", "");
      } else {
        say("Could not read a device: " + (err && err.message ? err.message :
            String(err)), "warn");
      }
    });
  });
})();
