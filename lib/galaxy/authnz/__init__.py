"""
Contains implementations for authentication and authorization against an
OpenID Connect (OIDC) Identity Provider (IdP).

This package follows "authorization code flow" authentication protocol to authenticate
Galaxy users against third-party identity providers.

Additionally, this package implements functionalist's to request temporary access
credentials for cloud-based resource providers (e.g., Amazon AWS, Microsoft Azure).
"""

import importlib
import logging
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import ParseError

log = logging.getLogger(__name__)


class IdentityProvider(object):
    """
    OpenID Connect Identity Provider abstract interface.
    """

    def __init__(self, provider, config):
        """
        Initialize the identity provider using the provided configuration,
        and raise a ParseError (or any more related specific exception) in
        case the configuration is malformed.

        :type provider: string
        :param provider: is the name of the identity provider (e.g., Google).

        :type config: xml.etree.ElementTree.Element
        :param config: Is the configuration element of the provider
            from the configuration file (e.g., oidc_config.xml).
            This element contains the all the provider-specific
            configuration elements.
        """
        raise NotImplementedError()

    def authenticate(self, trans):
        """Runs for authentication process. Checks the database if a
        valid identity exists in the database; if yes, then the  user
        is authenticated, if not, it generates a provider-specific
        authentication flow and returns redirect URI to the controller.

        :type trans: GalaxyWebTransaction
        :param trans: Galaxy web transaction.

        :return: a redirect URI to the provider's authentication
            endpoint.
        """
        raise NotImplementedError()

    def callback(self, state_token, authz_code, trans):
        """
        Handles authentication call-backs from identity providers.
        This process maps `state-token` to a user
        :type state_token: string
        :param state_token: is an anti-forgery token which identifies
            a Galaxy user to whom the given authorization code belongs to.
        :type authz_code: string
        :param authz_code: a very short-lived, single-use token to
            request a refresh token.
        :type trans: GalaxyWebTransaction
        :param trans: Galaxy web transaction.
        :return boolean:
            True: if callback is handled successfully.
            False: if processing callback fails, then Galaxy attempts re-authentication.
        """
        raise NotImplementedError()

    def disconnect(self, provider, trans, redirect_url=None):
        raise NotImplementedError()


class AuthnzManager(object):

    def __init__(self, app, oidc_config_file, oidc_backends_config_file):
        """
        :type app: galaxy.app.UniverseApplication
        :param app:

        :type config: string
        :param config: sets the path for OIDC configuration
            file (e.g., oidc_backends_config.xml).
        """
        self._parse_oidc_config(oidc_config_file)
        self._parse_oidc_backends_config(oidc_backends_config_file)

    def _parse_oidc_config(self, config_file):
        self.oidc_config = {}
        try:
            tree = ET.parse(config_file)
            root = tree.getroot()
            if root.tag != 'OIDC':
                raise ParseError("The root element in OIDC_Config xml file is expected to be `OIDC`, "
                                 "found `{}` instead -- unable to continue.".format(root.tag))
            for child in root:
                if child.tag != 'Setter':
                    log.error("Expect a node with `Setter` tag, found a node with `{}` tag instead; "
                              "skipping this node.".format(child.tag))
                    continue
                if 'Property' not in child.attrib or 'Value' not in child.attrib or 'Type' not in child.attrib:
                    log.error("Could not find the node attributes `Property` and/or `Value` and/or `Type`;"
                              " found these attributes: `{}`; skipping this node.".format(child.attrib))
                    continue
                try:
                    func = getattr(importlib.import_module('__builtin__'), child.get('Type'))
                except AttributeError:
                    log.error("The value of attribute `Type`, `{}`, is not a valid built-in type;"
                              " skipping this node").format(child.get('Type'))
                    continue
                self.oidc_config[child.get('Property')] = func(child.get('Value'))
        except ImportError:
            raise
        except ParseError as e:
            raise ParseError("Invalid configuration at `{}`: {} -- unable to continue.".format(config_file, e.message))

    def _parse_oidc_backends_config(self, config_file):
        self.providers = {}
        try:
            tree = ET.parse(config_file)
            root = tree.getroot()
            if root.tag != 'OIDC':
                raise ParseError("The root element in OIDC config xml file is expected to be `OIDC`, "
                                 "found `{}` instead -- unable to continue.".format(root.tag))
            for child in root:
                if child.tag != 'provider':
                    log.error("Expect a node with `provider` tag, found a node with `{}` tag instead; "
                              "skipping the node.".format(child.tag))
                    continue
                if 'name' not in child.attrib:
                    log.error("Could not find a node attribute 'name'; skipping the node '{}'.".format(child.tag))
                    continue
                provider = child.get('name')
                try:
                    from .psa_authnz import PSAAuthnz
                    self.providers[provider] = PSAAuthnz(provider, self.oidc_config, child)
                # TODO: capture exception of type `Exception` here, these are the type of errors which can raise if anything goes wrong initializing the provider.
                except ParseError:
                    log.error("Could not initialize `{}` identity provider; skipping this node.".format(provider))
                    continue
                # except Exception as e:
                #     raise Exception(e.message)
            if len(self.providers) == 0:
                raise ParseError("No valid provider configuration parsed.")
        except ImportError:
            raise
        except ParseError as e:
            raise ParseError("Invalid configuration at `{}`: {} -- unable to continue.".format(config_file, e.message))
        # except Exception as e:
        #     raise Exception("Malformed OIDC Configuration XML -- unable to continue. {}".format(e.message))

    def authenticate(self, provider, trans):
        """
        :type provider: string
        :param provider: set the name of the identity provider to be
            used for authentication flow.
        :type trans: GalaxyWebTransaction
        :param trans: Galaxy web transaction.
        :return: an identity provider specific authentication redirect URI.
        """
        if provider in self.providers:
            try:
                return self.providers[provider].authenticate(trans)
            except:
                raise
        else:
            log.error("The provider '{}' is not a recognized and expected provider.".format(provider))

    def callback(self, provider, state_token, authz_code, trans):
        if provider in self.providers:
            try:
                return self.providers[provider].callback(state_token, authz_code, trans)
            except:
                raise
        else:
            raise NameError("The provider '{}' is not a recognized and expected provider.".format(provider))

    def disconnect(self, provider, trans, redirect_url=None):
        return self.providers[provider].disconnect(provider, trans, redirect_url)
