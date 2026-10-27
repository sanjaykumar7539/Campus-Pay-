"""Implement against the selected scanner SDK. This contract cannot authorize scans."""


class Scanner:
    def open(self):
        raise NotImplementedError("Choose a real scanner and implement its SDK adapter before use")

    def capture(self, job, timeout_seconds):
        """Return None on timeout, otherwise:
        {capture_id: unique acquisition ID, matched: bool, finger_ref: opaque reference}.

        ENROLL: supervised capture/enrollment; both stages must be the same finger.
        PAY: 1:N match against that institution's enrolled fingers.
        The reference MUST be stable across all authorized scanners in the institution.
        Never return a student-entered ID as match proof. Never send images/templates.
        Require a physical finger lift before any subsequent acquisition.
        """
        raise NotImplementedError

    def release(self, job):
        """Wait for finger removal and discard transient scan buffers."""
        raise NotImplementedError

    def close(self):
        pass
