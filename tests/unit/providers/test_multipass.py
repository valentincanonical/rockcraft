# -*- Mode:Python; indent-tabs-mode:nil; tab-width:4 -*-
#
# Copyright 2021 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import pathlib
import re
from unittest import mock
from unittest.mock import call

import pytest
from craft_providers import bases
from craft_providers.multipass import MultipassError, MultipassInstallationError

from rockcraft import providers
from rockcraft.providers import ProviderError


@pytest.fixture()
def mock_buildd_base_configuration():
    with mock.patch(
        "rockcraft.providers._multipass.RockcraftBuilddBaseConfiguration", autospec=True
    ) as mock_base_config:
        yield mock_base_config


@pytest.fixture
def mock_confirm_with_user():
    with mock.patch(
        "rockcraft.providers._multipass.confirm_with_user",
        return_value=False,
    ) as mock_confirm:
        yield mock_confirm


@pytest.fixture
def mock_multipass(monkeypatch):
    with mock.patch(
        "craft_providers.multipass.Multipass", autospec=True
    ) as mock_client:
        yield mock_client.return_value


@pytest.fixture(autouse=True)
def mock_multipass_ensure_multipass_is_ready():
    with mock.patch(
        "craft_providers.multipass.ensure_multipass_is_ready", return_value=None
    ) as mock_is_ready:
        yield mock_is_ready


@pytest.fixture()
def mock_multipass_install():
    with mock.patch("craft_providers.multipass.install") as mock_install:
        yield mock_install


@pytest.fixture(autouse=True)
def mock_multipass_is_installed():
    with mock.patch(
        "craft_providers.multipass.is_installed", return_value=True
    ) as mock_is_installed:
        yield mock_is_installed


@pytest.fixture
def mock_multipass_launch():
    with mock.patch(
        "craft_providers.multipass.launch", autospec=True
    ) as mock_multipass_launch:
        yield mock_multipass_launch


def test_clean_project_environments_without_multipass(
    mock_multipass, mock_multipass_is_installed, mock_path
):
    mock_multipass_is_installed.return_value = False
    provider = providers.MultipassProvider(mock_multipass)

    assert (
        provider.clean_project_environments(
            project_name="my-rock",
            project_path=mock_path,
        )
        == []
    )

    assert mock_multipass_is_installed.mock_calls == [mock.call()]
    assert mock_multipass.mock_calls == []


def test_clean_project_environments(mock_multipass, mock_path):
    mock_multipass.list.return_value = [
        "do-not-delete-me-please",
        "rockcraft-testrock-445566",
        "rockcraft-my-rock",
        "rockcraft-my-rock-445566",
        "rockcraft-my-rock-project-445566",
        "rockcraft_445566_a",
    ]
    provider = providers.MultipassProvider(mock_multipass)

    assert provider.clean_project_environments(
        project_name="my-rock-project",
        project_path=mock_path,
    ) == ["rockcraft-my-rock-project-445566"]

    assert mock_multipass.mock_calls == [
        mock.call.list(),
        mock.call.delete(
            instance_name="rockcraft-my-rock-project-445566",
            purge=True,
        ),
    ]

    mock_multipass.reset_mock()

    assert provider.clean_project_environments(
        project_name="testrock",
        project_path=mock_path,
    ) == ["rockcraft-testrock-445566"]

    assert mock_multipass.mock_calls == [
        mock.call.list(),
        mock.call.delete(
            instance_name="rockcraft-testrock-445566",
            purge=True,
        ),
    ]

    mock_multipass.reset_mock()

    assert (
        provider.clean_project_environments(
            project_name="unknown-rock",
            project_path=mock_path,
        )
        == []
    )
    assert mock_multipass.mock_calls == [
        mock.call.list(),
    ]


def test_clean_project_environments_list_failure(mock_multipass, mock_path):
    error = MultipassError(brief="fail")
    mock_multipass.list.side_effect = error
    provider = providers.MultipassProvider(mock_multipass)

    with pytest.raises(ProviderError, match="fail") as raised:
        provider.clean_project_environments(
            project_name="rock",
            project_path=mock_path,
        )

    assert raised.value.__cause__ is error


def test_clean_project_environments_delete_failure(mock_multipass, mock_path):
    error = MultipassError(brief="fail")
    mock_multipass.list.return_value = ["rockcraft-testrock-445566"]
    mock_multipass.delete.side_effect = error
    provider = providers.MultipassProvider(mock_multipass)

    with pytest.raises(ProviderError, match="fail") as raised:
        provider.clean_project_environments(
            project_name="testrock",
            project_path=mock_path,
        )

    assert raised.value.__cause__ is error


def test_ensure_provider_is_available_ok_when_installed(mock_multipass_is_installed):
    mock_multipass_is_installed.return_value = True
    provider = providers.MultipassProvider()

    provider.ensure_provider_is_available()


def test_ensure_provider_is_available_errors_when_user_declines(
    mock_confirm_with_user, mock_multipass_is_installed
):
    mock_confirm_with_user.return_value = False
    mock_multipass_is_installed.return_value = False
    provider = providers.MultipassProvider()

    match = re.escape(
        "Multipass is required, but not installed. Visit https://multipass.run/ for "
        "instructions on installing Multipass for your operating system."
    )
    with pytest.raises(ProviderError, match=match):
        provider.ensure_provider_is_available()

    assert mock_confirm_with_user.mock_calls == [
        mock.call(
            "Multipass is required, but not installed. "
            "Do you wish to install Multipass and configure it with the defaults?",
            default=False,
        )
    ]


def test_ensure_provider_is_available_errors_when_multipass_install_fails(
    mock_confirm_with_user, mock_multipass_is_installed, mock_multipass_install
):
    error = MultipassInstallationError("foo")
    mock_confirm_with_user.return_value = True
    mock_multipass_is_installed.return_value = False
    mock_multipass_install.side_effect = error
    provider = providers.MultipassProvider()

    match = re.escape(
        "Failed to install Multipass. Visit https://multipass.run/ for "
        "instructions on installing Multipass for your operating system."
    )
    with pytest.raises(ProviderError, match=match) as raised:
        provider.ensure_provider_is_available()

    assert mock_confirm_with_user.mock_calls == [
        mock.call(
            "Multipass is required, but not installed. "
            "Do you wish to install Multipass and configure it with the defaults?",
            default=False,
        )
    ]
    assert raised.value.__cause__ is error


def test_ensure_provider_is_available_errors_when_multipass_not_ready(
    mock_confirm_with_user,
    mock_multipass_is_installed,
    mock_multipass_install,
    mock_multipass_ensure_multipass_is_ready,
):
    error = MultipassError(
        brief="some error", details="some details", resolution="some resolution"
    )
    mock_confirm_with_user.return_value = True
    mock_multipass_is_installed.return_value = True
    mock_multipass_ensure_multipass_is_ready.side_effect = error
    provider = providers.MultipassProvider()

    with pytest.raises(
        ProviderError,
        match=re.escape("some error\nsome details\nsome resolution"),
    ) as raised:
        provider.ensure_provider_is_available()

    assert raised.value.__cause__ is error


def test_get_command_environment_minimal(monkeypatch):
    monkeypatch.setenv("IGNORE_ME", "or-im-failing")
    monkeypatch.setenv("PATH", "not-using-host-path")
    provider = providers.MultipassProvider()

    env = provider.get_command_environment()

    assert env == {
        "ROCKCRAFT_MANAGED_MODE": "1",
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin",
    }


def test_get_instance_name(mock_path):
    provider = providers.MultipassProvider()

    assert (
        provider.get_instance_name(
            project_name="my-project-name",
            project_path=mock_path,
        )
        == "rockcraft-my-project-name-445566"
    )


def test_get_command_environment_all_opts(monkeypatch):
    monkeypatch.setenv("IGNORE_ME", "or-im-failing")
    monkeypatch.setenv("PATH", "not-using-host-path")
    monkeypatch.setenv("http_proxy", "test-http-proxy")
    monkeypatch.setenv("https_proxy", "test-https-proxy")
    monkeypatch.setenv("no_proxy", "test-no-proxy")
    provider = providers.MultipassProvider()

    env = provider.get_command_environment()

    assert env == {
        "ROCKCRAFT_MANAGED_MODE": "1",
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin",
        "http_proxy": "test-http-proxy",
        "https_proxy": "test-https-proxy",
        "no_proxy": "test-no-proxy",
    }


@pytest.mark.parametrize(
    "name,expected_valid,expected_reason",
    [
        ("ubuntu:18.04", True, None),
        ("ubuntu:20.04", True, None),
        (
            "ubuntu:19.04",
            False,
            "Base 'ubuntu:19.04' is not supported (must be 'ubuntu:18.04' or 'ubuntu:20.04')",
        ),
    ],
)
def test_is_base_available(name, expected_valid, expected_reason):
    provider = providers.MultipassProvider()

    valid, reason = provider.is_base_available(name)

    assert (valid, reason) == (expected_valid, expected_reason)


@pytest.mark.parametrize("is_installed", [True, False])
def test_is_provider_available(is_installed, mock_multipass_is_installed):
    mock_multipass_is_installed.return_value = is_installed
    provider = providers.MultipassProvider()

    assert provider.is_provider_available() == is_installed


@pytest.mark.parametrize(
    "channel,alias",
    [("18.04", bases.BuilddBaseAlias.BIONIC), ("20.04", bases.BuilddBaseAlias.FOCAL)],
)
def test_launched_environment(
    channel,
    alias,
    mock_buildd_base_configuration,
    mock_multipass_launch,
    monkeypatch,
    tmp_path,
    mock_path,
):
    expected_environment = {
        "ROCKCRAFT_MANAGED_MODE": "1",
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin",
    }

    provider = providers.MultipassProvider()

    with provider.launched_environment(
        project_name="test-rock",
        project_path=mock_path,
        base=f"ubuntu:{channel}",
    ) as instance:
        assert instance is not None
        assert mock_multipass_launch.mock_calls == [
            mock.call(
                name="rockcraft-test-rock-445566",
                base_configuration=mock_buildd_base_configuration.return_value,
                image_name=f"snapcraft:ubuntu-{channel}",
                cpus=2,
                disk_gb=64,
                mem_gb=2,
                auto_clean=True,
            ),
            mock.call().mount(
                host_source=mock_path, target=pathlib.Path("/root/project")
            ),
        ]
        assert mock_buildd_base_configuration.mock_calls == [
            call(
                alias=alias,
                environment=expected_environment,
                hostname="rockcraft-test-rock-445566",
            )
        ]

        mock_multipass_launch.reset_mock()

    assert mock_multipass_launch.mock_calls == [
        mock.call().unmount_all(),
        mock.call().stop(),
    ]


def test_launched_environment_unmounts_and_stops_after_error(
    mock_buildd_base_configuration, mock_multipass_launch, tmp_path
):
    provider = providers.MultipassProvider()

    with pytest.raises(RuntimeError):
        with provider.launched_environment(
            project_name="test-rock",
            project_path=tmp_path,
            base="ubuntu:20.04",
        ):
            mock_multipass_launch.reset_mock()
            raise RuntimeError("this is a test")

    assert mock_multipass_launch.mock_calls == [
        mock.call().unmount_all(),
        mock.call().stop(),
    ]


def test_launched_environment_launch_base_configuration_error(
    mock_buildd_base_configuration, mock_multipass_launch, tmp_path
):
    error = bases.BaseConfigurationError(brief="fail")
    mock_multipass_launch.side_effect = error
    provider = providers.MultipassProvider()

    with pytest.raises(ProviderError, match="fail") as raised:
        with provider.launched_environment(
            project_name="test-rock",
            project_path=tmp_path,
            base="ubuntu:20.04",
        ):
            pass

    assert raised.value.__cause__ is error


def test_launched_environment_launch_multipass_error(
    mock_buildd_base_configuration, mock_multipass_launch, tmp_path
):
    error = MultipassError(brief="fail")
    mock_multipass_launch.side_effect = error
    provider = providers.MultipassProvider()

    with pytest.raises(ProviderError, match="fail") as raised:
        with provider.launched_environment(
            project_name="test-rock",
            project_path=tmp_path,
            base="ubuntu:20.04",
        ):
            pass

    assert raised.value.__cause__ is error


def test_launched_environment_unmount_all_error(
    mock_buildd_base_configuration, mock_multipass_launch, tmp_path
):
    error = MultipassError(brief="fail")
    mock_multipass_launch.return_value.unmount_all.side_effect = error
    provider = providers.MultipassProvider()

    with pytest.raises(ProviderError, match="fail") as raised:
        with provider.launched_environment(
            project_name="test-rock",
            project_path=tmp_path,
            base="ubuntu:20.04",
        ):
            pass

    assert raised.value.__cause__ is error


def test_launched_environment_stop_error(
    mock_buildd_base_configuration, mock_multipass_launch, tmp_path
):
    error = MultipassError(brief="fail")
    mock_multipass_launch.return_value.stop.side_effect = error
    provider = providers.MultipassProvider()

    with pytest.raises(ProviderError, match="fail") as raised:
        with provider.launched_environment(
            project_name="test-rock",
            project_path=tmp_path,
            base="ubuntu:20.04",
        ):
            pass

    assert raised.value.__cause__ is error
