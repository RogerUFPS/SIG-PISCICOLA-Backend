from apps.farms.permissions import HasFarmPermission


class CanManageMonitoring(HasFarmPermission):
    pass


__all__ = ["CanManageMonitoring"]
