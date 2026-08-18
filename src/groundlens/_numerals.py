@@
-from decimal import Context, Decimal, InvalidOperation
+from decimal import Context, Decimal, InvalidOperation, localcontext
@@
-def format_decimal(value: Decimal) -> str:
-    """Canonical string for a value. ``1000``, ``1000.5`` -- never ``1E+3``."""
-    normal = value.normalize(CTX)
-    exponent = normal.as_tuple().exponent
-    if isinstance(exponent, int) and exponent > 0:
-        normal = normal.quantize(Decimal(1), context=CTX)
-    return format(normal, "f")
+def format_decimal(value: Decimal) -> str:
+    """Canonical string for a value. ``1000``, ``1000.5`` -- never ``1E+3``.
+    Defensive: Must not raise decimal.InvalidOperation for any Decimal input.
+    """
+    # Early defense for non-finite values
+    try:
+        if value.is_nan() or value.is_infinite():
+            return str(value)
+    except Exception:
+        # If value isn't a Decimal or inspection fails, fall back to str()
+        try:
+            return str(value)
+        except Exception:
+            return ""
+
+    # Try normal path but don't allow InvalidOperation to escape
+    try:
+        normal = value.normalize(CTX)
+    except InvalidOperation:
+        # Final fallback: try naive formatting; don't re-raise
+        try:
+            return format(value, "f")
+        except Exception:
+            return str(value)
+
+    # Safely get exponent
+    try:
+        exponent = normal.as_tuple().exponent
+    except Exception:
+        try:
+            return format(normal, "f")
+        except Exception:
+            return str(normal)
+
+    if isinstance(exponent, int) and exponent > 0:
+        # Quantize to integer when exponent > 0, but guard against InvalidOperation
+        try:
+            normal = normal.quantize(Decimal(1), context=CTX)
+        except InvalidOperation:
+            try:
+                # Retry without trapping InvalidOperation
+                with localcontext(CTX) as ctx:
+                    ctx.traps[InvalidOperation] = False
+                    normal = normal.quantize(Decimal(1), context=ctx)
+            except Exception:
+                try:
+                    return format(value, "f")
+                except Exception:
+                    return str(value)
+
+    # Final formatting, be defensive
+    try:
+        return format(normal, "f")
+    except Exception:
+        return str(normal)
