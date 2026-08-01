"""Connexion à l'instance Kili on-premise.

Ce module est le seul endroit du dépôt qui instancie un client Kili.
Il ne masque pas le SDK : il se contente de lire la configuration et de
renvoyer un objet `Kili` standard, sur lequel les exemples appellent
directement les méthodes officielles (`create_project`, `assets`, ...).
"""

from kili.client import Kili

from kili_examples.config import settings


class MissingKiliCredentialsError(RuntimeError):
    """Levée quand KILI_API_KEY ou KILI_API_ENDPOINT est absent."""


def get_kili() -> Kili:
    """Instancier un client Kili à partir du fichier `.env`.

    Les identifiants ne sont jamais codés en dur : ils proviennent de
    `KILI_API_KEY` et `KILI_API_ENDPOINT` (voir `.env.example`).

    Returns:
        Un client Kili authentifié contre l'instance on-premise.

    Raises:
        MissingKiliCredentialsError: Si l'une des deux variables
            d'environnement est absente ou vide. On échoue tôt et avec un
            message explicite plutôt que de laisser le SDK produire une
            erreur réseau difficile à interpréter.
    """
    missing = [
        name
        for name, value in (
            ("KILI_API_KEY", settings.kili_api_key),
            ("KILI_API_ENDPOINT", settings.kili_api_endpoint),
        )
        if not value
    ]
    if missing:
        raise MissingKiliCredentialsError(
            f"Variable(s) manquante(s) : {', '.join(missing)}. "
            "Copiez .env.example vers .env et renseignez les valeurs de "
            "votre instance Kili on-premise."
        )

    # `api_endpoint` est indispensable en on-premise : sans lui, le SDK
    # viserait l'instance SaaS de Kili.
    return Kili(
        api_key=settings.kili_api_key,
        api_endpoint=settings.kili_api_endpoint,
    )
