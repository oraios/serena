package util;

/** Interface for service classes. **/
interface IService {
    /** Get the name of the service. **/
    public function getServiceName():String;

    /** Execute the service action. **/
    public function execute():Void;
}
