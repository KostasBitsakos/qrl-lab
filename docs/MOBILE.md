# Dashboard από το κινητό (Tailscale Serve)

Κανένα port δεν ανοίγει στο ίντερνετ· μόνο οι συσκευές του tailnet σου φτάνουν στις υπηρεσίες.
Οι εντολές `tailscale serve` **δεν έχουν επαληθευτεί** (το tailscale δεν ήταν εγκατεστημένο όταν γράφτηκε το κείμενο)·
αν κάποιο flag διαφέρει, δες `tailscale serve --help`.

## Βήματα (στη VM)
1. `sudo tailscale serve --bg 8501` → dashboard στο `https://<vm>.<tailnet>.ts.net`
2. `sudo tailscale serve --bg --https 8443 http://127.0.0.1:8502` → web terminal
3. `sudo tailscale serve --bg --https 8444 http://10.0.1.28:32000` → Grafana
4. `sudo tailscale serve --bg --https 8445 http://10.0.1.28:30000` → Prometheus UI

Έλεγχος: `tailscale serve status`.

## Άνοιγμα στο κινητό
Εγκατάσταση Tailscale app, login με τον ίδιο λογαριασμό, και άνοιγμα του `https://<vm>.<tailnet>.ts.net`.
Το dashboard βλέπει το host `*.ts.net` και φτιάχνει μόνο του τα links/iframes προς τις θύρες 8443-8445.
Το terminal ανοίγει από το tab «Terminal» (token στο URL, όπως πριν). Η sidebar είναι κλειστή σε μικρές οθόνες.
Αν το Grafana frame μένει κενό: χρειάζεται `allow_embedding` και ίσως `root_url` του Grafana στο ts.net URL.

## Ασφάλεια
- Μόνο συσκευές του tailnet σου. Ενεργοποίησε 2FA στον λογαριασμό identity provider.
- **Ποτέ `tailscale funnel`** (θα το έκανε δημόσιο).
- Το dashboard μένει στο 127.0.0.1:8501 και το terminal στο 127.0.0.1:8502 με token· το websocket δέχεται μόνο
  origins localhost ή `https://*.ts.net`.
- Το terminal είναι πλήρες shell της VM: κλείσ' το όταν τελειώσεις.

## Αναίρεση
- `sudo tailscale serve --https 8445 off` (ομοίως 8444, 8443)
- `sudo tailscale serve --https 443 off` (το dashboard) ή `sudo tailscale serve reset` για όλα
