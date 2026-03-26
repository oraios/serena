package model;

import util.Helper;
import util.IService;

/** A user with a name and role, implementing IService. **/
class User implements IService {
    var name:String;
    var role:Role;

    public function new(name:String, role:Role) {
        this.name = name;
        this.role = role;
    }

    public function getName():String {
        return name;
    }

    public function getRole():Role {
        return role;
    }

    public function getDisplayName():String {
        return Helper.formatMessage(name);
    }

    public function getServiceName():String {
        return "UserService";
    }

    public function execute():Void {
        trace('Executing service for user: ${getName()}');
    }
}
