# Tilt: rebuild/restart the bot automatically as you edit.  `tilt up` (UI at http://localhost:10350), `tilt down`.
#
#   src/** changes        → synced into the running container, process restarted (~1 s, no image rebuild)
#   pyproject/uv.lock     → dependencies re-synced inside the container, then restart
#   Dockerfile            → full image rebuild
#   .env changes          → containers recreated with the new environment
#
# Resources: bot (:3978, what Teams talks to), dev (:3979, docs + smoke target), tunnel (devtunnel host),
# smoke (manual trigger: runs scripts/smoke_local.py against dev).

# This Tiltfile only drives Docker Compose — no Kubernetes resources are defined — but Tilt still inspects the
# active kubeconfig context and refuses to run if it looks like production. Allow whatever is current.
allow_k8s_contexts(k8s_context())

load('ext://dotenv', 'dotenv')
dotenv()  # exposes .env values to this Tiltfile (TUNNEL_NAME below); compose reads .env itself

# The certificate is injected as base64 (same as `make docker-run`) so it never lands in an image layer.
pfx = local('base64 -i certs/bot.pfx', quiet=True, echo_off=True) if os.path.exists('certs/bot.pfx') else ''
os.putenv('CERT_PFX_BASE64', str(pfx).strip())

docker_build(
    'teams-bot',
    context='.',
    dockerfile='Dockerfile',
    only=['pyproject.toml', 'uv.lock', 'src'],
    live_update=[
        sync('./src', '/app/src'),
        run('cd /app && uv sync --locked --no-dev', trigger=['pyproject.toml', 'uv.lock']),
        restart_container(),
    ],
)

docker_compose('docker-compose.yml', profiles=['dev'])
watch_file('.env')

dc_resource('bot', labels=['bot'], resource_deps=[])
dc_resource('dev', labels=['bot'])

tunnel = os.getenv('TUNNEL_NAME', '')
if tunnel:
    local_resource(
        'tunnel',
        serve_cmd='devtunnel host %s' % tunnel,
        labels=['ingress'],
        readiness_probe=probe(exec=exec_action(['sh', '-c', 'curl -sf http://localhost:3978/company/bot/v1/health >/dev/null'])),
        resource_deps=['bot'],
    )
else:
    print('TUNNEL_NAME not set in .env — skipping the dev tunnel resource')

local_resource(
    'smoke',
    cmd='uv run scripts/smoke_local.py --bot http://localhost:3979 --connector-host host.docker.internal',
    labels=['tests'],
    resource_deps=['dev'],
    trigger_mode=TRIGGER_MODE_MANUAL,
    auto_init=False,
)
