# Deploying the site to Azure Static Web Apps (Free plan)

**Deployed on 25 Oct 2026:** https://calm-pond-0e514280f.3.azurestaticapps.net (resource group
`rg-scouts-eye`, app `scouts-eye`, Free plan). West Europe refused new Static Web Apps
("region not accepting new customers"), so the app lives in **East US 2**; the content is
served from the global edge anyway. The `Microsoft.Web` resource provider had to be
registered once on the subscription.

The site in `site/` is static (HTML/CSS/JS + JSON under `site/data/`). It never
calls Azure OpenAI or Foundry from the browser and contains no secrets; live
narration is never run from the public site. `site/staticwebapp.config.json`
holds the routes, caching and security headers.

Build output folder: `site/` (no build step; run `python3 build_site.py` first
to refresh `site/data/`).

## Option A – SWA CLI from this Mac (after `az login`)

```bash
# one-time: resource group and the Static Web App (Free plan, West Europe)
az group create --name rg-scouts-eye --location westeurope
az provider register --namespace Microsoft.Web --wait
az staticwebapp create --name scouts-eye --resource-group rg-scouts-eye --location eastus2 --sku Free   # westeurope was refused

# deploy the folder (the deployment token is read on the fly, never stored in the repo)
npx @azure/static-web-apps-cli@2 deploy --app-location ./site --output-location . \
  --deployment-token "$(az staticwebapp secrets list --name scouts-eye --resource-group rg-scouts-eye --query properties.apiKey -o tsv)" \
  --env production

# the public URL
az staticwebapp show --name scouts-eye --resource-group rg-scouts-eye --query defaultHostname -o tsv
```

What the owner has to click or approve: nothing in the portal; `az login`
must be valid, and `npx` downloads the SWA CLI (Node.js ≥ 18 must be
installed – check with `node --version`). The deployment token is printed
only into the shell variable above.

## Option B – GitHub Actions from the public repository

In the Azure portal: *Create a resource → Static Web App → Free*, source
GitHub, repository `laczmartin/scouts-eye`, branch `main`, build preset
*Custom*, app location `site`, output location `.` (empty api location). Azure
then opens a pull request / commits a workflow like the one below and stores
the deployment token as the repository secret
`AZURE_STATIC_WEB_APPS_API_TOKEN_...`. Every push to `main` redeploys.

```yaml
name: Azure Static Web Apps CI/CD
on:
  push:
    branches: [main]
  pull_request:
    types: [opened, synchronize, reopened, closed]
    branches: [main]
jobs:
  build_and_deploy:
    if: github.event_name == 'push' || (github.event_name == 'pull_request' && github.event.action != 'closed')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Azure/static-web-apps-deploy@v1
        with:
          azure_static_web_apps_api_token: ${{ secrets.AZURE_STATIC_WEB_APPS_API_TOKEN }}
          repo_token: ${{ secrets.GITHUB_TOKEN }}
          action: upload
          app_location: site
          output_location: .
          skip_app_build: true
```

Owner clicks: the portal wizard (GitHub authorisation of the Azure Static Web
Apps app once, repository selection, "Review + create").

## Cost

Static Web Apps **Free** plan: 0 USD (100 GB bandwidth / month, 250 MB app
size limit – the site is about 2.2 MB, custom domain and SSL included). No
other Azure resource is created; the Foundry project is not used by the site.
