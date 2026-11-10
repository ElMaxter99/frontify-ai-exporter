# FAQ

**Is it free? / ¿Es gratis?** Yes, Apache-2.0: use, modify and redistribute, also commercially. / Sí, Apache-2.0.

**Is it official / affiliated with Frontify? / ¿Es oficial?** No. Independent community project ([DISCLAIMER](../DISCLAIMER.md)). / No, es un proyecto independiente.

**Why Apache-2.0 and not MIT? / ¿Por qué Apache-2.0 y no MIT?** It is just as permissive, but adds an explicit patent licence, a clear contribution clause and an explicit "no trademark rights" statement — useful for a tool that mentions someone else's brand. / Igual de permisiva, pero añade licencia de patentes explícita, cláusula de contribuciones y declara que no concede derechos de marca.

**Where does my token go? / ¿Adónde va mi token?** Only to your Frontify domain, from memory/environment. Never stored, never logged, never sent to the CDN. / Solo a tu dominio de Frontify; nunca se guarda ni se registra.

**Can I run it against several clients? / ¿Varios clientes?** Yes: run it once per client with a different `--name`; each gets its own folder. / Sí, una ejecución por cliente con otro `--name`.

**What if my export is incomplete? / ¿Y si la exportación sale incompleta?** Read `EXPORT_REPORT.json` (`not_exported`, `scan_errors`, `inaccessible_due_to_permissions_or_api`). Usually token permissions or download-protected assets. Re-run: it resumes. / Revisa el informe; relanzar reanuda.

**Does it modify anything in Frontify? / ¿Modifica algo en Frontify?** No: it only issues read queries. / No, solo lecturas.

**Does it work with design tokens/components? / ¿Tokens y componentes?** Frontify's public GraphQL API doesn't expose them; see README "Real API limits". / La API pública no los expone.

**Has it been tested on a real Frontify? / ¿Probado en Frontify real?** Not yet — tests use a simulated API. Please report your results. / Aún no; se agradece tu feedback.
