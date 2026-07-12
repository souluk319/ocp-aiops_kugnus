from __future__ import annotations

import base64

from collections.abc import Callable, Mapping
from typing import Any


PORTAL_NAME = "komsco-ai-core-standalone"
PORTAL_CONFIGMAP_NAME = f"{PORTAL_NAME}-nginx"
PORTAL_SERVICE_CERT_SECRET = f"{PORTAL_NAME}-cert"
PORTAL_OAUTH_SECRET = f"{PORTAL_NAME}-oauth"
PORTAL_ROUTE_NAME = "cywell-aiops-standalone"


def resolved_credentials(
    target_namespace: str,
    secret_value_reader: Callable[[str, str, str], str],
    default_client_secret: str,
    default_cookie_secret: str,
) -> tuple[str, str]:
    client_secret = (
        secret_value_reader(target_namespace, PORTAL_OAUTH_SECRET, "client-secret")
        or default_client_secret
    )
    cookie_secret = (
        secret_value_reader(target_namespace, PORTAL_OAUTH_SECRET, "cookie-secret")
        or default_cookie_secret
    )
    return client_secret, cookie_secret


def secret_values(
    target_namespace: str,
    name: str,
    keys: list[str],
    secret_value_reader: Callable[[str, str, str], str],
) -> dict[str, str]:
    values: dict[str, str] = {}
    for key in keys:
        value = secret_value_reader(target_namespace, name, key)
        if value:
            values[key] = value
    return values


def configmap_value(
    target_namespace: str,
    name: str,
    key: str,
    resource_reader: Callable[[str, str, str, str | None], dict[str, Any] | None],
) -> str:
    try:
        existing = resource_reader("v1", "ConfigMap", name, target_namespace)
    except Exception:
        return ""
    if not isinstance(existing, Mapping):
        return ""
    data = existing.get("data")
    if not isinstance(data, Mapping):
        return ""
    value = data.get(key)
    return value if isinstance(value, str) else ""


def _secret_plain_value(secret: Mapping[str, Any] | None, key: str) -> str:
    if not isinstance(secret, Mapping):
        return ""
    string_data = secret.get("stringData")
    if isinstance(string_data, Mapping):
        value = string_data.get(key)
        if isinstance(value, str) and value:
            return value
    data = secret.get("data")
    if not isinstance(data, Mapping):
        return ""
    encoded = data.get(key)
    if not isinstance(encoded, str) or not encoded:
        return ""
    try:
        return base64.b64decode(encoded, validate=True).decode("utf-8")
    except Exception:
        return ""


def nginx_config(target_namespace: str) -> str:
    gateway_host = f"komsco-ai-gateway.{target_namespace}.svc"
    gateway_url = f"https://{gateway_host}:8443"
    return f"""worker_processes auto;
pid /tmp/nginx.pid;
events {{ worker_connections 1024; }}
http {{
  include /etc/nginx/mime.types;
  default_type application/octet-stream;
  access_log /dev/stdout;
  error_log /dev/stderr warn;
  client_body_temp_path /tmp/client_temp;
  proxy_temp_path /tmp/proxy_temp;
  fastcgi_temp_path /tmp/fastcgi_temp;
  uwsgi_temp_path /tmp/uwsgi_temp;
  scgi_temp_path /tmp/scgi_temp;
  sendfile on;
  server {{
    listen 8080;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;
    location = /healthz {{ add_header Content-Type text/plain; return 200 "ok\\n"; }}
    location = /readyz {{
      proxy_pass {gateway_url};
      proxy_ssl_server_name on;
      proxy_ssl_name {gateway_host};
      proxy_ssl_trusted_certificate /var/run/configmaps/service-ca/service-ca.crt;
      proxy_ssl_verify on;
      proxy_set_header Authorization "Bearer $http_x_forwarded_access_token";
      proxy_set_header Host $host;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto https;
    }}
    location /v1/ {{
      proxy_pass {gateway_url};
      proxy_http_version 1.1;
      proxy_ssl_server_name on;
      proxy_ssl_name {gateway_host};
      proxy_ssl_trusted_certificate /var/run/configmaps/service-ca/service-ca.crt;
      proxy_ssl_verify on;
      proxy_set_header Authorization "Bearer $http_x_forwarded_access_token";
      proxy_set_header Host $host;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto https;
    }}
    location / {{ try_files $uri $uri/ /index.html; }}
  }}
}}
"""


def oauth_client_resource(
    labels: Mapping[str, str],
    client_name: str,
    client_secret: str,
    host: str,
) -> dict[str, Any]:
    return {
        "apiVersion": "oauth.openshift.io/v1",
        "kind": "OAuthClient",
        "metadata": {"name": client_name, "labels": dict(labels)},
        "secret": client_secret,
        "redirectURIs": [f"https://{host}/oauth/callback"],
        "grantMethod": "prompt",
    }


def credentials_secret(
    labels: Mapping[str, str],
    target_namespace: str,
    client_secret: str,
    cookie_secret: str,
) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": PORTAL_OAUTH_SECRET,
            "namespace": target_namespace,
            "labels": dict(labels),
        },
        "type": "Opaque",
        "stringData": {
            "client-secret": client_secret,
            "cookie-secret": cookie_secret,
        },
    }


def portal_service_account(labels: Mapping[str, str], target_namespace: str) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "ServiceAccount",
        "metadata": {
            "name": PORTAL_NAME,
            "namespace": target_namespace,
            "labels": dict(labels),
        },
    }


def portal_configmap(labels: Mapping[str, str], target_namespace: str) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": PORTAL_CONFIGMAP_NAME,
            "namespace": target_namespace,
            "labels": dict(labels),
        },
        "data": {"nginx.conf": nginx_config(target_namespace)},
    }


def portal_service(labels: Mapping[str, str], target_namespace: str) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": PORTAL_NAME,
            "namespace": target_namespace,
            "labels": dict(labels),
            "annotations": {
                "service.beta.openshift.io/serving-cert-secret-name": PORTAL_SERVICE_CERT_SECRET,
            },
        },
        "spec": {
            "type": "ClusterIP",
            "selector": {"app": PORTAL_NAME},
            "ports": [{"name": "https", "port": 443, "targetPort": "oauth"}],
        },
    }


def portal_deployment(
    config: Mapping[str, Any],
    labels: Mapping[str, str],
) -> dict[str, Any]:
    target_namespace = str(config["namespace"])
    host = str(config["standaloneHost"])
    client_name = str(config["standaloneOAuthClientName"])
    pod_labels = {**dict(labels), "app": PORTAL_NAME}
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": PORTAL_NAME,
            "namespace": target_namespace,
            "labels": dict(labels),
        },
        "spec": {
            "replicas": int(config["standaloneReplicas"]),
            "selector": {"matchLabels": {"app": PORTAL_NAME}},
            "template": {
                "metadata": {"labels": pod_labels},
                "spec": {
                    "serviceAccountName": PORTAL_NAME,
                    "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
                    "containers": [
                        {
                            "name": "portal",
                            "image": str(config["standaloneImage"]),
                            "imagePullPolicy": "Always",
                            "ports": [{"containerPort": 8080, "name": "portal"}],
                            "readinessProbe": {
                                "httpGet": {"path": "/healthz", "port": "portal"},
                                "initialDelaySeconds": 2,
                                "periodSeconds": 5,
                            },
                            "securityContext": {
                                "allowPrivilegeEscalation": False,
                                "capabilities": {"drop": ["ALL"]},
                                "readOnlyRootFilesystem": True,
                                "runAsNonRoot": True,
                            },
                            "volumeMounts": [
                                {
                                    "name": "nginx",
                                    "mountPath": "/etc/nginx/nginx.conf",
                                    "subPath": "nginx.conf",
                                    "readOnly": True,
                                },
                                {
                                    "name": "service-ca",
                                    "mountPath": "/var/run/configmaps/service-ca",
                                    "readOnly": True,
                                },
                                {"name": "portal-tmp", "mountPath": "/tmp"},
                            ],
                        },
                        {
                            "name": "oauth-proxy",
                            "image": str(config["oauthProxyImage"]),
                            "imagePullPolicy": "IfNotPresent",
                            "args": [
                                "--provider=openshift",
                                "--https-address=:8443",
                                "--http-address=",
                                f"--client-id={client_name}",
                                "--client-secret-file=/etc/oauth/config/client-secret",
                                f"--redirect-url=https://{host}/oauth/callback",
                                "--upstream=http://127.0.0.1:8080",
                                "--tls-cert=/etc/tls/private/tls.crt",
                                "--tls-key=/etc/tls/private/tls.key",
                                "--cookie-secret-file=/etc/oauth/config/cookie-secret",
                                "--cookie-name=_cywell_aiops_oauth",
                                "--cookie-expire=24h0m0s",
                                "--scope=user:full",
                                "--email-domain=*",
                                "--skip-provider-button=true",
                                "--pass-access-token=true",
                                "--pass-user-bearer-token=true",
                                "--pass-user-headers=true",
                            ],
                            "ports": [{"containerPort": 8443, "name": "oauth"}],
                            "readinessProbe": {
                                "httpGet": {"path": "/oauth/healthz", "port": "oauth", "scheme": "HTTPS"},
                                "initialDelaySeconds": 3,
                                "periodSeconds": 5,
                            },
                            "securityContext": {
                                "allowPrivilegeEscalation": False,
                                "capabilities": {"drop": ["ALL"]},
                                "readOnlyRootFilesystem": True,
                                "runAsNonRoot": True,
                            },
                            "volumeMounts": [
                                {"name": "tls", "mountPath": "/etc/tls/private", "readOnly": True},
                                {"name": "oauth", "mountPath": "/etc/oauth/config", "readOnly": True},
                                {"name": "oauth-tmp", "mountPath": "/tmp"},
                            ],
                        },
                    ],
                    "volumes": [
                        {"name": "nginx", "configMap": {"name": PORTAL_CONFIGMAP_NAME}},
                        {"name": "service-ca", "configMap": {"name": "komsco-ai-service-ca"}},
                        {"name": "tls", "secret": {"secretName": PORTAL_SERVICE_CERT_SECRET}},
                        {"name": "oauth", "secret": {"secretName": PORTAL_OAUTH_SECRET}},
                        {"name": "portal-tmp", "emptyDir": {}},
                        {"name": "oauth-tmp", "emptyDir": {}},
                    ],
                },
            },
        },
    }


def portal_network_policy(labels: Mapping[str, str], target_namespace: str) -> dict[str, Any]:
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {
            "name": f"{PORTAL_NAME}-ingress",
            "namespace": target_namespace,
            "labels": dict(labels),
        },
        "spec": {
            "podSelector": {"matchLabels": {"app": PORTAL_NAME}},
            "policyTypes": ["Ingress"],
            "ingress": [
                {
                    "from": [
                        {
                            "namespaceSelector": {
                                "matchLabels": {"network.openshift.io/policy-group": "ingress"}
                            }
                        }
                    ],
                    "ports": [{"port": 8443, "protocol": "TCP"}],
                }
            ],
        },
    }


def portal_route(
    config: Mapping[str, Any],
    labels: Mapping[str, str],
    route_tls: Mapping[str, str],
    destination_ca: str,
) -> dict[str, Any] | None:
    certificate = route_tls.get("tls.crt", "")
    key = route_tls.get("tls.key", "")
    if not certificate or not key or not destination_ca:
        return None
    tls: dict[str, Any] = {
        "termination": "reencrypt",
        "insecureEdgeTerminationPolicy": "Redirect",
        "certificate": certificate,
        "key": key,
        "destinationCACertificate": destination_ca,
    }
    if route_tls.get("ca.crt"):
        tls["caCertificate"] = route_tls["ca.crt"]
    return {
        "apiVersion": "route.openshift.io/v1",
        "kind": "Route",
        "metadata": {
            "name": PORTAL_ROUTE_NAME,
            "namespace": str(config["namespace"]),
            "labels": dict(labels),
        },
        "spec": {
            "host": str(config["standaloneHost"]),
            "to": {"kind": "Service", "name": PORTAL_NAME, "weight": 100},
            "port": {"targetPort": "https"},
            "tls": tls,
            "wildcardPolicy": "None",
        },
    }


def readiness_conditions(
    config: Mapping[str, Any],
    generation: int,
    *,
    condition: Callable[..., dict[str, Any]],
    deployment_condition: Callable[..., dict[str, Any]],
    service_condition: Callable[..., dict[str, Any]],
    lookup_condition: Callable[..., tuple[dict[str, Any], dict[str, Any] | None]],
    resource_reader: Callable[[str, str, str, str | None], dict[str, Any] | None],
) -> dict[str, dict[str, Any]]:
    if not bool(config["standaloneEnabled"]):
        return {
            "StandalonePortalReady": condition(
                "StandalonePortalReady",
                "True",
                "DisabledBySpec",
                "Standalone portal is disabled by AIOpsInstallation spec.",
                generation,
            ),
            "StandaloneRouteReady": condition(
                "StandaloneRouteReady",
                "True",
                "DisabledBySpec",
                "Standalone Route is disabled by AIOpsInstallation spec.",
                generation,
            ),
            "StandaloneOAuthReady": condition(
                "StandaloneOAuthReady",
                "True",
                "DisabledBySpec",
                "Standalone OAuth client is disabled by AIOpsInstallation spec.",
                generation,
            ),
            "ApplicationLauncherReady": condition(
                "ApplicationLauncherReady",
                "True",
                "StandaloneDisabled",
                "Standalone Application Menu readiness is not required by this installation.",
                generation,
            ),
        }

    target_namespace = str(config["namespace"])
    portal_ready = deployment_condition(
        "StandalonePortalReady", PORTAL_NAME, target_namespace, generation
    )
    if portal_ready["status"] == "True":
        portal_ready = service_condition(
            "StandalonePortalReady", PORTAL_NAME, target_namespace, generation
        )
    if portal_ready["status"] == "True":
        portal_ready = condition(
            "StandalonePortalReady",
            "True",
            "PortalAvailable",
            f"Standalone portal deployment and service are ready in {target_namespace}.",
            generation,
        )

    route_ready, route = lookup_condition(
        "StandaloneRouteReady",
        "route.openshift.io/v1",
        "Route",
        PORTAL_ROUTE_NAME,
        target_namespace,
        generation,
    )
    approved_tls = resource_reader(
        "v1",
        "Secret",
        str(config["standaloneTlsSecretName"]),
        target_namespace,
    )
    approved_certificate = _secret_plain_value(approved_tls, "tls.crt")
    approved_key = _secret_plain_value(approved_tls, "tls.key")
    if not approved_certificate or not approved_key:
        route_ready = condition(
            "StandaloneRouteReady",
            "False",
            "ApprovedTLSSecretMissing",
            f"Approved TLS Secret {target_namespace}/{config['standaloneTlsSecretName']} is missing or incomplete.",
            generation,
        )
    elif route_ready["status"] == "False":
        route_ready["reason"] = "RouteOrTLSPending"
        route_ready["message"] = (
            f"Route is waiting for approved TLS Secret {target_namespace}/"
            f"{config['standaloneTlsSecretName']} and service CA data."
        )
    elif route_ready["status"] == "True" and route is not None:
        spec = route.get("spec") if isinstance(route.get("spec"), Mapping) else {}
        tls = spec.get("tls") if isinstance(spec.get("tls"), Mapping) else {}
        route_target = spec.get("to") if isinstance(spec.get("to"), Mapping) else {}
        destination_ca = configmap_value(
            target_namespace,
            "komsco-ai-service-ca",
            "service-ca.crt",
            resource_reader,
        )
        if (
            spec.get("host") == config["standaloneHost"]
            and route_target.get("name") == PORTAL_NAME
            and tls.get("termination") == "reencrypt"
            and tls.get("certificate") == approved_certificate
            and tls.get("key") == approved_key
            and bool(destination_ca)
            and tls.get("destinationCACertificate") == destination_ca
        ):
            route_ready = condition(
                "StandaloneRouteReady",
                "True",
                "RouteConfigured",
                f"Standalone Route serves https://{config['standaloneHost']} with the approved TLS Secret and re-encrypt destination CA.",
                generation,
            )
        else:
            route_ready = condition(
                "StandaloneRouteReady",
                "False",
                "RouteMismatch",
                "Standalone Route does not match the configured host, service, or TLS termination.",
                generation,
            )

    client_name = str(config["standaloneOAuthClientName"])
    oauth_ready, oauth_client = lookup_condition(
        "StandaloneOAuthReady",
        "oauth.openshift.io/v1",
        "OAuthClient",
        client_name,
        None,
        generation,
    )
    if oauth_ready["status"] == "True" and oauth_client is not None:
        redirect_uris = oauth_client.get("redirectURIs")
        expected_redirect = f"https://{config['standaloneHost']}/oauth/callback"
        if isinstance(redirect_uris, list) and expected_redirect in redirect_uris:
            oauth_ready = condition(
                "StandaloneOAuthReady",
                "True",
                "OAuthClientConfigured",
                f"OAuthClient {client_name} has the approved callback URI.",
                generation,
            )
        else:
            oauth_ready = condition(
                "StandaloneOAuthReady",
                "False",
                "RedirectMismatch",
                f"OAuthClient {client_name} does not contain the approved callback URI.",
                generation,
            )

    if not bool(config["consoleApplicationMenuEnabled"]):
        launcher_ready = condition(
            "ApplicationLauncherReady",
            "True",
            "DisabledBySpec",
            "Application Menu link is disabled by AIOpsInstallation spec.",
            generation,
        )
    else:
        name = str(config["consoleApplicationMenuName"])
        launcher_ready, console_link = lookup_condition(
            "ApplicationLauncherReady",
            "console.openshift.io/v1",
            "ConsoleLink",
            name,
            None,
            generation,
        )
        if launcher_ready["status"] == "True" and console_link is not None:
            spec = (
                console_link.get("spec")
                if isinstance(console_link.get("spec"), Mapping)
                else {}
            )
            expected_href = f"https://{config['standaloneHost']}"
            if spec.get("location") == "ApplicationMenu" and spec.get("href") == expected_href:
                launcher_ready = condition(
                    "ApplicationLauncherReady",
                    "True",
                    "LauncherConfigured",
                    f"Application Menu opens {expected_href}.",
                    generation,
                )
            else:
                launcher_ready = condition(
                    "ApplicationLauncherReady",
                    "False",
                    "LauncherMismatch",
                    "Application Menu link does not target the configured AIOps portal.",
                    generation,
                )

    return {
        "StandalonePortalReady": portal_ready,
        "StandaloneRouteReady": route_ready,
        "StandaloneOAuthReady": oauth_ready,
        "ApplicationLauncherReady": launcher_ready,
    }


def resources_for_standalone(
    config: Mapping[str, Any],
    labels: Mapping[str, str],
    client_secret: str,
    cookie_secret: str,
    route_tls: Mapping[str, str],
    destination_ca: str,
) -> list[dict[str, Any]]:
    if not bool(config["standaloneEnabled"]):
        return []
    target_namespace = str(config["namespace"])
    resources = [
        portal_service_account(labels, target_namespace),
        portal_configmap(labels, target_namespace),
        credentials_secret(labels, target_namespace, client_secret, cookie_secret),
        portal_service(labels, target_namespace),
        oauth_client_resource(
            labels,
            str(config["standaloneOAuthClientName"]),
            client_secret,
            str(config["standaloneHost"]),
        ),
        portal_deployment(config, labels),
        portal_network_policy(labels, target_namespace),
    ]
    route = portal_route(config, labels, route_tls, destination_ca)
    if route is not None:
        resources.append(route)
    return resources
