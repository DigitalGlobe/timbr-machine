import React from 'react';
import dispatcher from './dispatcher.js';

class DisplayStatus extends React.Component {

  constructor( props ) {
    super( props );
    this.state = { 
      status: {}
    };
  }

  toggle() {
    this.props.comm.send({ 
      method: 'toggle', 
      data: { 
        action: this.state.status.running ? 'stop' : 'start' } 
      }, this.props.cell.get_callbacks() );
  }

  componentWillMount(){
    dispatcher.register( payload => {
      if ( payload.actionType === 'display_update' ) {
        this.setState({ status: payload.data.status })
      }
    } );
  }

  render() {
    const { status } = this.state;

    const action = status.running ? 'Stop' : 'Start';

    return ( 
      <div id="timbr_machine_status">
        <div className="timbr-header">
          <span className="timbr-title">Timbr Machine Status</span>
          <button onClick={ () => this.toggle.apply(this) }>{ action }</button>
        </div>
        { Object.keys( status ).map( ( field, i ) => (
            <div key={ i }>
              <span className='field-name'>{field}:</span>
              <span>{ status[ field ] }</span>
            </div>
          ))
        }
      </div>
    );
  }
}

export default DisplayStatus;
