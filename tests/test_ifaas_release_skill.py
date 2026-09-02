import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / ".agents" / "plugins" / "plugins" / "ifaas-release" / "skills" / "ifaas-release"


class IfaasReleaseSkillTests(unittest.TestCase):
    def test_skill_is_explicit_only_and_has_no_mcp_dependency(self):
        policy = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        instructions = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: false", policy)
        self.assertIn("普通修改、提交、推送、构建或自然语言打包请求均不触发", instructions)
        self.assertIn("第一阶段使用本地 CLI/HTTP，不依赖 MCP", instructions)

    def test_plugin_metadata_requires_explicit_skill_name(self):
        manifest_path = SKILL_ROOT.parents[1] / ".codex-plugin" / "plugin.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        serialized = json.dumps(manifest["interface"], ensure_ascii=False)
        self.assertIn("$ifaas-release", serialized)
        self.assertNotIn("MCP", serialized)

    def test_installer_does_not_register_mcp(self):
        installer = (SKILL_ROOT.parents[1] / "scripts" / "install.ps1").read_text(encoding="utf-8")
        self.assertNotIn("codex mcp", installer.lower())
        self.assertIn("IFAAS_BUILD_PLATFORM_URL", installer)


if __name__ == "__main__":
    unittest.main()
